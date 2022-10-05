import sys
import os
import json
import time
import numpy as np
import struct
import PyQt5
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot, QCoreApplication
from dastardcommander import rpc_client, status_monitor

class LevelTrigConfig(QtWidgets.QDialog):

    header_fmt = "<HBBIIffQQ"
    data_fmt = ["b", "B", "<h", "<H", "<i", "<I", "<q", "<Q"]

    def __init__(self, parent=None):
        self.dcom = parent
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        uifile = os.path.join(os.path.dirname(__file__), "ui/level_trigger_config.ui")
        PyQt5.uic.loadUi(uifile, self)

        self.textBrowser.setReadOnly(True)
        self.zmqlistener = None
        self.zmqthread = None
        self.startButton.clicked.connect(self.startConfiguration)

    @pyqtSlot()
    def startConfiguration(self):
        self.positivePulseButton.setDisabled(True)
        self.negativePulseButton.setDisabled(True)
        self.levelSpinBox.setDisabled(True)
        self.startButton.setDisabled(True)

        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()

        self.cursor = self.textBrowser.textCursor()
        self.cursor.insertText(f"Configuring level triggers at {threshold:+d}...\n")

        self.cursor.insertText("1) Stopping all triggers.\n")
        prev_trig_state = self.dcom.triggerTab.trigger_state.copy()
        if not self.zeroTriggers():
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        self.cursor.insertText("2) Turning on 50 ms autotriggers.\n")
        if not self.autoTriggers():
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        self.launchRecordMonitor()

        # 3) Collect baseline level data
        # 4) Return triggers to previous state (maybe zero them first?)
        self.cursor.insertText("Done! You may close this window.\n")

    def launchRecordMonitor(self):
        self.channels_seen = {}
        self.zmqthread = QtCore.QThread()
        self.zmqlistener = status_monitor.ZMQListener(self.dcom.host, 1+self.dcom.port)
        self.zmqlistener.pulserecord.connect(self.updateReceived)

        self.zmqlistener.moveToThread(self.zmqthread)
        self.zmqthread.started.connect(self.zmqlistener.data_monitor_loop)
        QtCore.QTimer.singleShot(0, self.zmqthread.start)

    @pyqtSlot()
    def done(self, dialogCode):
        """Cleanly close the zmqlistener before closing the dialog."""
        if self.zmqlistener is not None:
            self.zmqlistener.running = False
        if self.zmqthread is not None:
            self.zmqthread.quit()
            self.zmqthread.wait()
        super().done(dialogCode)

    def zeroTriggers(self):
        ids = self.dcom.channelIndicesAll()
        if len(ids) == 0:
            return False
        config = {
            "ChannelIndices": ids,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True

    def autoTriggers(self):
        ids = self.dcom.channelIndicesAll()
        if len(ids) == 0:
            return False
        config = {
            "ChannelIndices": ids,
            "AutoTrigger": True,
            "AutoDelay": 50,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True

    @pyqtSlot(bytes, bytes)
    def updateReceived(self, header, data_message):
        try:
            values = struct.unpack(self.header_fmt, header)
            chanidx = values[0]
            typecode = values[2]
            data_fmt = self.data_fmt[typecode]
            nsamp = values[4]
            # data = struct.unpack(data_fmt, data_message)
            data = np.frombuffer(data_message, dtype=data_fmt)
            if chanidx not in self.channels_seen:
                self.channels_seen[chanidx] = True
                print("Data from chan {:4d}: {}".format(chanidx, data[:10]))

        except Exception as e:
            print("Error processing pulse record is: %s" % e)
            return
