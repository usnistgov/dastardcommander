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

        positive = self.positivePulseButton.isChecked()
        signmessage = "falling"
        if positive:
            signmessage = "rising"
        threshold = self.levelSpinBox.value()

        self.textBrowser.clear()
        self.cursor = self.textBrowser.textCursor()
        self.cursor.insertText(f"Configuring {signmessage} edge triggers at threshold {threshold} ...\n")
        self.save_quiet = "TRIGGER" in self.dcom.quietTopics
        if not self.save_quiet:
            self.dcom.quietTopics.add("TRIGGER")
            print("Will suppress printing of TRIGGER status until disabling hyperactive channels is complete.")

        self.cursor.insertText("1) Stopping all triggers.\n")
        if not self.zeroAllTriggers():
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        self.cursor.insertText("2) Turning on edge triggers.\n")
        channels_to_configure = self.dcom.triggerTabSimple.channelIndicesSignalOnly(exclude_blocked=True)
        if not self.startEdgeTriggers(channels_to_configure):
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        # 3) Collect trigger rate data
        staleTriggerRateMessageID, msg = self.dcom.lastTriggerRateMessage
        trigcounts = np.zeros(len(msg["CountsSeen"]), dtype=np.int)
        duration = 0.0
        t0 = time.time()
        integration_time = 5.0
        self.cursor.insertText(f"3) Collecting trigger rate data (takes ~{integration_time} seconds).\n")

        while True:
            time.sleep(0.25)
            triggerRateMessageID, msg = self.dcom.lastTriggerRateMessage
            if triggerRateMessageID != staleTriggerRateMessageID:
                triggerRateMessageID = staleTriggerRateMessageID
                if "CountsSeen" in msg:
                    trigcounts += msg["CountsSeen"]
                    duration += msg["Duration"]

            if time.time() - t0 > integration_time:
                break

        rates = trigcounts / duration
        disable = []
        enable = []
        too_many_triggers = 1.0  # i.e. 1.0 triggers per second or more is bad when x rays are off
        for idx, rate in enumerate(rates):
            if rate < too_many_triggers:
                enable.append(idx)
            else:
                disable.append(idx)

        # 4) Return triggers to previous state (maybe zero them first?)
        self.cursor.insertText("4) Data complete; stopping all triggers.\n")
        self.zeroAllTriggers()
        nd = len(disable)
        self.cursor.insertText(f"5) Disabling {nd} channels; sending edge triggers to all others.\n")
        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()
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
                "EdgeRising": positive,
                "EdgeFalling": not positive,
                "EdgeLevel": threshold,
                "LevelTrigger": False,
                }
            self.dcom.client.call("SourceControl.ConfigureTriggers", ts)

        if not self.save_quiet:
            delay = 5000 # ms
            QtCore.QTimer.singleShot(delay, self.endSilentTRIGGER)
        self.cursor.insertText("Done! You may close this window.\n")

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
        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()
        config = {
            "ChannelIndices": channels_to_configure,
            "EdgeTrigger": True,
            "EdgeRising": positive,
            "EdgeFalling": not positive,
            "EdgeLevel": threshold,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True
