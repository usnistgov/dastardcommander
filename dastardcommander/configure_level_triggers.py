import sys
import os
import json
import time
import PyQt5
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot, QCoreApplication
from dastardcommander import rpc_client, status_monitor

class LevelTrigConfig(QtWidgets.QDialog):
    def __init__(self, parent=None):
        self.dcom = parent
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        uifile = os.path.join(os.path.dirname(__file__), "ui/level_trigger_config.ui")
        PyQt5.uic.loadUi(uifile, self)

        self.textBrowser.setReadOnly(True)
        self.cursor = self.textBrowser.textCursor()
        self.cursor.insertText("Configuring level triggers...\n")

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
        # 4) Return triggers to previous state (maybe zero them first?)
        self.cursor.insertText("Done! You may close this window.\n")

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
