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

class DisableHyperDialog(QtWidgets.QDialog):

    dataComplete = pyqtSignal()

    def __init__(self, parent=None):
        self.dcom = parent
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        uifile = os.path.join(os.path.dirname(__file__), "ui/disable_hyperactive_dialog.ui")
        PyQt5.uic.loadUi(uifile, self)

        self.textBrowser.setReadOnly(True)
        self.startButton.clicked.connect(self.startConfiguration)
#         self.dataComplete.connect(self.finishConfiguration)

    @pyqtSlot()
    def startConfiguration(self):
        self.positivePulseButton.setDisabled(True)
        self.negativePulseButton.setDisabled(True)
        self.levelSpinBox.setDisabled(True)
        self.startButton.setDisabled(True)

        self.textBrowser.clear()
        self.cursor = self.textBrowser.textCursor()

        self.thread = QtCore.QThread()
        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()
        self.worker = DisableHyperWorker(self.dcom, positive, threshold)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.message.connect(self.reportProgress)
        self.thread.start()

    @pyqtSlot(str)
    def reportProgress(self, message):
        self.cursor.insertText(message)


class DisableHyperWorker(QtCore.QObject):
    """QObject that can run in a QThread to keep GUI (main) thread responsive."""

    finished = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, dcom, positive, threshold):
        self.dcom = dcom
        self.positive = positive
        self.threshold = threshold
        super().__init__()

    def run(self):
        signmessage = "falling"
        if self.positive:
            signmessage = "rising"
        self.message.emit(f"Configuring {signmessage} edge triggers at threshold {self.threshold} ...\n")

        self.save_quiet = "TRIGGER" in self.dcom.quietTopics
        if not self.save_quiet:
            self.dcom.quietTopics.add("TRIGGER")
            print("Will suppress printing of TRIGGER status until disabling hyperactive channels is complete.")

        self.message.emit("1) Stopping all triggers.\n")
        if not self.zeroAllTriggers():
            self.message.emit("X  Failed: no channels known.\n")
            self.finished.emit()
            return

        self.message.emit("2) Turning on edge triggers.\n")
        channels_to_configure = self.dcom.triggerTabSimple.channelIndicesSignalOnly(exclude_blocked=True)
        if not self.startEdgeTriggers(channels_to_configure):
            self.message.emit("X  Failed: no channels known.\n")
            self.finished.emit()
            return

        # 3) Collect trigger rate data
        staleTriggerRateMessageID, msg = self.dcom.lastTriggerRateMessage
        trigcounts = np.zeros(len(msg["CountsSeen"]), dtype=np.int)
        duration = 0.0
        t0 = time.time()
        integration_time = 5.0
        self.message.emit(f"3) Collecting trigger rate data (takes ~{integration_time} seconds).\n")

        while True:
            time.sleep(0.25)
            triggerRateMessageID, msg = self.dcom.lastTriggerRateMessage
            if triggerRateMessageID != staleTriggerRateMessageID:
                triggerRateMessageID = staleTriggerRateMessageID
                if "CountsSeen" in msg and "Duration" in msg:
                    trigcounts += msg["CountsSeen"]
                    duration += msg["Duration"]

            if time.time() - t0 > integration_time:
                break

        duration /= 1e9  # convert ns to seconds
        if duration <= 0:
            self.message.emit(f"X  Failed: no trigger rate messages were received in {integration_time} seconds.")
            self.finished.emit()
            return

        print("counts: ", trigcounts)
        rates = trigcounts / duration
        print("rates: ", rates)
        disable = []
        enable = []
        too_many_triggers = 1.0  # i.e. 1.0 triggers per second or more is bad when x rays are off
        for idx, rate in enumerate(rates):
            if rate < too_many_triggers:
                enable.append(idx)
            else:
                disable.append(idx)

        nd = len(disable)
        self.message.emit(f"4) Disabling {nd} channels; re-asserting edge triggers to all others.\n")
        if len(disable) > 0:
            ts = {
                "ChannelIndices": disable,
                "AutoTrigger": False,
                "EdgeTrigger": False,
                "LevelTrigger": False,
                }
            self.dcom.client.call("SourceControl.ConfigureTriggers", ts)
        if len(enable) > 0:
            ts = {
                "ChannelIndices": enable,
                "AutoTrigger": False,
                "EdgeTrigger": True,
                "EdgeRising": self.positive,
                "EdgeFalling": not self.positive,
                "EdgeLevel": self.threshold,
                "LevelTrigger": False,
                }
            self.dcom.client.call("SourceControl.ConfigureTriggers", ts)

        if not self.save_quiet:
            delay = 5000 # ms
            QtCore.QTimer.singleShot(delay, self.endSilentTRIGGER)
        self.message.emit("Done! You may close this window.\n")
        self.finished.emit()

    @pyqtSlot()
    def endSilentTRIGGER(self):
        if not self.save_quiet:
            self.dcom.quietTopics.remove("TRIGGER")

    def zeroAllTriggers(self):
        ids = self.dcom.channelIndicesAll()
        if len(ids) == 0:
            return False
        config = {
            "ChannelIndices": ids,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True

    def startEdgeTriggers(self, channels_to_configure):
        if len(channels_to_configure) == 0:
            return False
        config = {
            "ChannelIndices": channels_to_configure,
            "EdgeTrigger": True,
            "EdgeRising": self.positive,
            "EdgeFalling": not self.positive,
            "EdgeLevel": self.threshold,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True
