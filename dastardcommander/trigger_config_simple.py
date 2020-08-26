# Qt5 imports
import PyQt5.uic
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QSettings

# other non qt imports
import os
from enum import Enum
import numpy as np
import time

"""keep track of the state of sync between the GUI and dastard"""
class Sync(Enum):
    UNKNOWN = 0
    PULSE = 1
    NOISE = 2

TWO_TRIGGER_RECORD_OPTIONS = ["Zero records", "Two overlapping full length records", "Two shorter records"]


class TriggerConfigSimple(QtWidgets.QWidget):
    """Provide a simple trigger UI designed for doing the same thing everyday with the fewest choices."""

    def __init__(self, parent, dcom):
        QtWidgets.QWidget.__init__(self, parent)
        self.client = dcom.client
        self.dcom = dcom
        self.settings = QSettings()
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/trigger_config_simple.ui"), self)
        
        self.readSettings()
        self.connect()
        self.setSync(Sync.UNKNOWN)
        self._lastSentConfig = None
        self._lastSentConfigTime = None

    def setupCombo(self):
        for i, t in enumerate(TWO_TRIGGER_RECORD_OPTIONS):
            self.comboBox_twoTriggers.setItemText(i, t)

    def connect(self):
        self.spinBox_recordLength.valueChanged.connect(self.handleRecordLengthOrPercentPretrigChange)
        self.spinBox_pretrigLength.valueChanged.connect(self.handlePretrigLengthChange)
        self.spinBox_percentPretrigger.valueChanged.connect(self.handleRecordLengthOrPercentPretrigChange)
        self.spinBox_level.valueChanged.connect(self.handleUIChange)
        self.spinBox_nMonotone.valueChanged.connect(self.handleUIChange)
        self.checkBox_disableZeroThreshold.stateChanged.connect(self.handleUIChange)
        self.comboBox_twoTriggers.currentIndexChanged.connect(self.handleUIChange)
        self.pushButton_sendPulse.clicked.connect(self.handleSendPulse)
        self.pushButton_sendNoise.clicked.connect(self.handleSendNoise)

    def handleRecordLengthOrPercentPretrigChange(self):
        rl = self.spinBox_recordLength.value()
        percent = self.spinBox_percentPretrigger.value()
        pt = (rl*percent/100)
        self.spinBox_pretrigLength.blockSignals(True)
        self.spinBox_pretrigLength.setValue(pt)
        self.spinBox_pretrigLength.blockSignals(False)
        self.setSync(Sync.UNKNOWN)

    def handlePretrigLengthChange(self):
        rl = self.spinBox_recordLength.value()
        pt = self.spinBox_pretrigLength.value()
        self.spinBox_percentPretrigger.blockSignals(True)
        self.spinBox_percentPretrigger.setValue(100*pt/rl)
        self.spinBox_percentPretrigger.blockSignals(False)       
        self.setSync(Sync.UNKNOWN)


    def handleSendNoise(self):
        self.setSync(Sync.NOISE)
        self.writeSettings() # there are no noise settings, but if there are in the future, we're good
        self.zeroAllTriggers()
        self.sendRecordLength()
        config = {
            "ChannelIndicies": self.channelIndiciesSignalOnlyWithExcludes(),
            "AutoTrigger": True
        }  
        self.client.call("SourceControl.ConfigureTriggers", config)
        self._lastSentConfig = config
        self._lastSentConfigTime = time.time()

    def handleSendPulse(self):
        self.setSync(Sync.PULSE)
        self.writeSettings()
        self.zeroAllTriggers()
        self.sendRecordLength()
        # first send the trigger mesage for all channels
        v = self.comboBox_twoTriggers.currentIndex()

        config = {
            "ChannelIndicies": self.channelIndiciesSignalOnlyWithExcludes(),
            "EdgeMulti": True,
            "EdgeMultiNoise": False,
            "EdgeMultiMakeShortRecords": v == 2,
            "EdgeMultiMakeContaminatedRecords": v == 1,
            "EdgeMultiVerifyNMonotone": self.spinBox_nMonotone.value(),
            "EdgeMultiLevel": self.spinBox_level.value()
        }
        self.client.call("SourceControl.ConfigureTriggers", config)
        self._lastSentConfig = config
        self._lastSentConfigTime = time.time()


    def handleUIChange(self):
        self.setSync(Sync.UNKNOWN)

    def setSync(self, sync: Sync):
        if sync == Sync.UNKNOWN:
            s = "Unknown"
        elif sync == Sync.PULSE:
            s = "Pulse"
        elif sync == Sync.NOISE:
            s = "Noise"
        else:
            raise Exception("wtf, thought I handled all of them")
        self.label_sync.setText(f"Current Trigger State: {s}")

    def readSettings(self):
        s = self.settings
        self.spinBox_recordLength.setValue(s.value("record_length", 1024))
        self.spinBox_pretrigLength.setValue(s.value("pretrigger_length", 512))
        self.spinBox_percentPretrigger.setValue(s.value("percent_pretrigger", 25.0))
        self.spinBox_level.setValue(s.value("level", 100))
        self.spinBox_nMonotone.setValue(s.value("n_monotone", 5))
        self.checkBox_disableZeroThreshold.setChecked(s.value("disable_zero_threshold", False))
        self.comboBox_twoTriggers.setCurrentIndex(s.value("two_triggers", 0))

    def writeSettings(self):
        s = self.settings
        s.setValue("record_length", self.spinBox_recordLength.value())
        s.setValue("pretrigger_length", self.spinBox_pretrigLength.value())
        s.setValue("percent_pretrigger", self.spinBox_percentPretrigger.value())
        s.setValue("level", self.spinBox_level.value())
        s.setValue("n_monotone", self.spinBox_nMonotone.value())
        s.setValue("disable_zero_threshold", self.checkBox_disableZeroThreshold.isChecked())
        s.setValue("two_triggers", self.comboBox_twoTriggers.currentIndex())
 
    def sendRecordLength(self):
        self.dcom.triggerTab.blockSignals(True)
        self.client.call("SourceControl.ConfigurePulseLengths",
                    {"Nsamp": self.spinBox_recordLength.value(), 
                    "Npre": self.spinBox_pretrigLength.value()})
        time.sleep(0.1)
        self.dcom.triggerTab.blockSignals(False)

    def zeroAllTriggers(self):
        config = {
            "ChannelIndicies": self.dcom.channelIndiciesAll(),
        }
        self.client.call("SourceControl.ConfigureTriggers", config)

    def channelIndiciesSignalOnlyWithExcludes(self):
        return self.dcom.channelIndiciesSignalOnly()
        # TODO: add exclude list, and maybe a way to auto populate it?

    def handleTriggerMessage(self, d, nmsg):
        """If DASTARD indicates the trigger state has changed, change the UI to say so."""
        # we assume any TRIGGER message more than 100 ms after this class changed the trigger settings 
        # has changed the state
        if self._lastSentConfigTime is None:
            return
        elapsed_s = time.time()-self._lastSentConfigTime
        if elapsed_s > 0.1:
            self.setSync(Sync.UNKNOWN)

    def handleNsamplesNpresamplesMessage(self, nsamp, npre):
        nsmatch = nsamp == self.spinBox_recordLength.value()
        nprematch = npre == self.spinBox_pretrigLength.value()
        if not (nsmatch and nprematch):
            self.setSync(Sync.UNKNOWN)
