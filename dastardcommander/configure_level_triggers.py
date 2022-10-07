import sys
import os
import json
import time
import numpy as np
import struct
import PyQt5
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot, pyqtSignal
from dastardcommander import rpc_client, status_monitor

class LevelTrigConfig(QtWidgets.QDialog):

    header_fmt = "<HBBIIffQQ"
    data_fmt = ["b", "B", "<h", "<H", "<i", "<I", "<q", "<Q"]

    dataComplete = pyqtSignal()

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
        self.dataComplete.connect(self.finishConfiguration)

    @pyqtSlot()
    def startConfiguration(self):
        self.positivePulseButton.setDisabled(True)
        self.negativePulseButton.setDisabled(True)
        self.levelSpinBox.setDisabled(True)
        self.startButton.setDisabled(True)

        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()
        self.recordsPerChan = 40

        self.cursor = self.textBrowser.textCursor()
        self.cursor.insertText(f"Configuring level triggers at (baseline{threshold:+d}) ...\n")
        self.save_quiet = "TRIGGER" in self.dcom.quietTopics
        if not self.save_quiet:
            self.dcom.quietTopics.add("TRIGGER")
            print("Will suppress printing of TRIGGER status until level triggers are configured.")

        self.cursor.insertText("1) Stopping all triggers.\n")
        prev_trig_state = self.dcom.triggerTab.trigger_state.copy()
        if not self.zeroTriggers():
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        self.cursor.insertText("2) Turning on 50 ms autotriggers.\n")
        if not self.autoTriggers():
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        # 3) Collect baseline level data
        self.cursor.insertText("3) Collecting baseline data (may take several seconds).\n")
        self.launchRecordMonitor()

    def launchRecordMonitor(self):
        self.channels_seen = {
            id:BaselineFinder(self.recordsPerChan) for id in self.dcom.channelIndicesSignalOnly()
        }
        self.nchanIncomplete = len(self.channels_seen)
        self.progressBar.setMaximum(self.recordsPerChan*self.nchanIncomplete)
        self.zmqthread = QtCore.QThread()
        self.zmqlistener = status_monitor.ZMQListener(self.dcom.host, 1+self.dcom.port)
        self.zmqlistener.pulserecord.connect(self.updateReceived)

        self.zmqlistener.moveToThread(self.zmqthread)
        self.zmqthread.started.connect(self.zmqlistener.data_monitor_loop)
        QtCore.QTimer.singleShot(0, self.zmqthread.start)

    @pyqtSlot()
    def finishConfiguration(self):
        # 4) Return triggers to previous state (maybe zero them first?)
        self.cursor.insertText("4) Done with baseline data.  Stopping all triggers.\n")
        self.zeroTriggers()
        self.cursor.insertText("5) Sending all level triggers\n")
        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()
        for idx,blf in self.channels_seen.items():
            level = int(0.5 + blf.baseline() + threshold)
            ts = {
                "ChannelIndices": [idx],
                "AutoTrigger": False,
                "EdgeTrigger": False,
                "LevelTrigger": True,
                "LevelRising": positive,
                "LevelLevel": level,
                }
            self.dcom.client.call("SourceControl.ConfigureTriggers", ts)
            time.sleep(0.01)

        if not self.save_quiet:
            delay = 5000 # ms
            QtCore.QTimer.singleShot(delay, self.endSilentTRIGGER)
        self.cursor.insertText("Done! You may close this window.\n")

    @pyqtSlot()
    def endSilentTRIGGER(self):
        if not self.save_quiet:
            self.dcom.quietTopics.remove("TRIGGER")

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
            "AutoDelay": 50000000,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True

    @pyqtSlot(bytes, bytes)
    def updateReceived(self, header, data_message):
        try:
            values = struct.unpack(self.header_fmt, header)
            chanidx = values[0]
            blf = self.channels_seen[chanidx]
            if blf.completed:
                return

            typecode = values[2]
            data_fmt = self.data_fmt[typecode]
            nsamp = values[4]
            data = np.frombuffer(data_message, dtype=data_fmt)
            blf.newValues(data)
            self.progressBar.setValue(self.progressBar.value()+1)
            if blf.completed:
                self.nchanIncomplete -= 1
            if self.nchanIncomplete <= 0:
                self.dataComplete.emit()

        except Exception as e:
            print("Error processing pulse record is: %s" % e)
            return


class BaselineFinder():
    """
    An object to estimate the baseline of a channel's data.
    Call `bf.newValues(data)` to add a new data record `data` to the history.
    Call `B=bf.baseline()` to estimate the baseline and return it.
    Check `bf.completed` to see if a sufficient amount of data has been acquired.
    """
    def __init__(self, recordsRequired=40):
        self.recordsRequired = recordsRequired
        self.medians = []
        self.completed = False

    def newValues(self, data):
        self.medians.append(np.median(data))
        if len(self.medians) >= self.recordsRequired:
            self.completed = True

    def baseline(self):
        return np.min(self.medians)
