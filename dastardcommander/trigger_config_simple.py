# Qt5 imports
import PyQt5.uic
from PyQt5 import QtWidgets
from PyQt5.QtCore import QSettings

# other non qt imports
import os
from enum import Enum
import time
from . import projectors

"""keep track of the state of sync between the GUI and dastard"""


class Sync(Enum):
    UNKNOWN = 0
    PULSE = 1
    NOISE = 2


class TwoPulseChoice(Enum):
    NO_RECORD = 0
    CONTAMINATED = 1
    VARIABLE_LENGTH = 2

    def to_str(self):
        if self == TwoPulseChoice.NO_RECORD:
            return "Zero records"
        elif self == TwoPulseChoice.CONTAMINATED:
            return "Two overlapping full length records"
        elif self == TwoPulseChoice.VARIABLE_LENGTH:
            return "Two shorter records"
        else:
            raise Exception()


class TriggerConfigSimple(QtWidgets.QWidget):
    """Provide a simple trigger UI designed for doing the same thing everyday with the fewest choices."""

    def __init__(self, parent, dcom):
        QtWidgets.QWidget.__init__(self, parent)
        self.client = dcom.client
        self.dcom = dcom
        self.settings = QSettings()
        PyQt5.uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui/trigger_config_simple.ui"), self
        )

        self.readSettings()
        self.connect()
        self.setPulseSync(Sync.UNKNOWN)
        self.setProjectorSync(False)
        self._lastSentConfig = None
        self._lastSentConfigTime = None

    def setupCombo(self):
        for i, t in enumerate(TwoPulseChoice):
            self.comboBox_twoTriggers.setItemText(i, t.to_str())

    def connect(self):
        self.spinBox_recordLength.valueChanged.connect(
            self.handleRecordLengthOrPercentPretrigChange
        )
        self.spinBox_pretrigLength.valueChanged.connect(self.handlePretrigLengthChange)
        self.spinBox_percentPretrigger.valueChanged.connect(
            self.handleRecordLengthOrPercentPretrigChange
        )
        self.spinBox_level.valueChanged.connect(self.handleUIChange)
        self.spinBox_nMonotone.valueChanged.connect(self.handleUIChange)
        self.checkBox_disableZeroThreshold.stateChanged.connect(self.handleUIChange)
        self.comboBox_twoTriggers.currentIndexChanged.connect(self.handleUIChange)
        self.pushButton_sendPulse.clicked.connect(self.handleSendPulse)
        self.pushButton_sendNoise.clicked.connect(self.handleSendNoise)
        self.pushButton_sendNone.clicked.connect(self.zeroAllTriggers)
        self.toolButton_chooseProjectors.clicked.connect(self.handleChooseProjectors)
        self.pushButton_sendProjectors.clicked.connect(self.handleSendProjectors)

    def handleRecordLengthOrPercentPretrigChange(self):
        rl = self.spinBox_recordLength.value()
        percent = self.spinBox_percentPretrigger.value()
        pt = rl * percent / 100
        self.spinBox_pretrigLength.blockSignals(True)
        self.spinBox_pretrigLength.setValue(pt)
        self.spinBox_pretrigLength.blockSignals(False)
        self.setPulseSync(Sync.UNKNOWN)

    def handlePretrigLengthChange(self):
        rl = self.spinBox_recordLength.value()
        pt = self.spinBox_pretrigLength.value()
        self.spinBox_percentPretrigger.blockSignals(True)
        self.spinBox_percentPretrigger.setValue(100 * pt / rl)
        self.spinBox_percentPretrigger.blockSignals(False)
        self.setPulseSync(Sync.UNKNOWN)

    def handleSendNoise(self):
        self.setPulseSync(Sync.NOISE)
        self.writeSettings()  # there are no noise settings, but if there are in the future, we're good
        self.zeroAllTriggers()
        self.sendRecordLength()
        config = {
            "ChannelIndices": self.channelIndicesSignalOnly(exclude_blocked=True),
            "AutoTrigger": True,
            "AutoDelay": 0,
        }
        print("Sending noise! To ", config["ChannelIndices"])
        self.client.call("SourceControl.ConfigureTriggers", config)
        self._lastSentConfig = config
        self._lastSentConfigTime = time.time()

    def handleSendPulse(self):
        self.writeSettings()
        self.zeroAllTriggers()
        self.sendRecordLength()
        # first send the trigger mesage for all channels
        s = self.comboBox_twoTriggers.currentText()
        print(s, "\n\n")

        config = {
            "ChannelIndices": self.channelIndicesSignalOnly(exclude_blocked=True),
            "EdgeMulti": True,
            "EdgeMultiNoise": False,
            "EdgeMultiMakeShortRecords": s == TwoPulseChoice.VARIABLE_LENGTH.to_str(),
            "EdgeMultiMakeContaminatedRecords": s
            == TwoPulseChoice.CONTAMINATED.to_str(),
            "EdgeMultiVerifyNMonotone": self.spinBox_nMonotone.value(),
            "EdgeMultiLevel": self.spinBox_level.value(),
            "EdgeMultiDisableZeroThreshold": self.checkBox_disableZeroThreshold.isChecked(),
        }
        self.client.call("SourceControl.ConfigureTriggers", config)
        self._lastSentConfig = config
        self._lastSentConfigTime = time.time()
        self.setPulseSync(Sync.PULSE)

    def handleUIChange(self):
        self.setPulseSync(Sync.UNKNOWN)

    def setPulseSync(self, sync: Sync):
        if sync == Sync.UNKNOWN:
            s = "Unknown"
        elif sync == Sync.PULSE:
            s = "Pulse"
        elif sync == Sync.NOISE:
            s = "Noise"
        else:
            raise Exception("wtf, thought I handled all of them")
        self.label_sync.setText(f"Current Trigger State: {s}")

    def setProjectorSync(self, b: bool):
        if b:
            s = "Sent"
        else:
            s = "Unknown"
        self.label_projectorsSync.setText(f"Projectors state: {s}")

    def readSettings(self):
        s = self.settings
        self.spinBox_recordLength.setValue(int(s.value("record_length", 1024)))
        self.spinBox_pretrigLength.setValue(int(s.value("pretrigger_length", 512)))
        self.spinBox_percentPretrigger.setValue(
            float(s.value("percent_pretrigger", 25.0))
        )
        self.spinBox_level.setValue(int(s.value("level", 100)))
        self.spinBox_nMonotone.setValue(int(s.value("n_monotone", 5)))
        # apparently QSettings sucks with bools, so use an int for the following
        v = int(s.value("disable_zero_threshold", 0))
        assert v == 1 or v == 0
        self.checkBox_disableZeroThreshold.setChecked(v == 1)
        self.comboBox_twoTriggers.setCurrentIndex(int(s.value("two_triggers", 0)))
        self.lineEdit_projectors.setText(s.value("projectors_file", ""))

    def writeSettings(self):
        s = self.settings
        s.setValue("record_length", self.spinBox_recordLength.value())
        s.setValue("pretrigger_length", self.spinBox_pretrigLength.value())
        s.setValue("percent_pretrigger", self.spinBox_percentPretrigger.value())
        s.setValue("level", self.spinBox_level.value())
        s.setValue("n_monotone", self.spinBox_nMonotone.value())
        s.setValue(
            "disable_zero_threshold",
            int(self.checkBox_disableZeroThreshold.isChecked()),
        )
        s.setValue("two_triggers", self.comboBox_twoTriggers.currentIndex())
        s.setValue("projectors_file", self.lineEdit_projectors.text())

    def sendRecordLength(self):
        self.dcom.triggerTab.blockSignals(True)
        self.client.call(
            "SourceControl.ConfigurePulseLengths",
            {
                "Nsamp": self.spinBox_recordLength.value(),
                "Npre": self.spinBox_pretrigLength.value(),
            },
        )
        time.sleep(0.1)
        self.dcom.triggerTab.blockSignals(False)

    def zeroAllTriggers(self):
        config = {
            "ChannelIndices": self.dcom.channelIndicesAll(),
        }
        self.client.call("SourceControl.ConfigureTriggers", config)

    def channelIndicesSignalOnly(self, exclude_blocked=True):
        """
        Return a sorted list of the channel indices that correspond to signal channels (i.e., 
        exclude the TDM error channels).
        If `exclude_blocked` is true, also exclude any listed in the self.triggerBlocker.special
        list of disabled channels.
        """
        signal_indices = self.dcom.channelIndicesSignalOnly()
        if not exclude_blocked:
            return signal_indices
        sigset = set(signal_indices)
        blocked_numbers = self.triggerBlocker.special
        blocked_indices = [self.channel_indices[n] for n in blocked_numbers]
        enabled_indices = list(sigset - set(blocked_indices))
        if len(enabled_indices) < len(sigset):
            print("{}/{} channels enabled and {} disabled: {}".format(len(enabled_indices), 
                len(sigset), len(sigset)-len(enabled_indices), blocked_indices))
        else:
            print("All {} channels are enabled; .".format(len(enabled_indices)))
            print("The disabled list is: ", blocked_indices)
        enabled_indices.sort()
        return enabled_indices

    def handleTriggerMessage(self, d):
        """If DASTARD indicates the trigger state has changed, change the UI to say so."""
        # we assume any TRIGGER message more than 100 ms after this class changed the trigger settings
        # has changed the state
        if self._lastSentConfigTime is None:
            return
        elapsed_s = time.time() - self._lastSentConfigTime
        if elapsed_s > 1.5:
            self.setPulseSync(Sync.UNKNOWN)

    def handleNsamplesNpresamplesMessage(self, nsamp, npre):
        nsmatch = nsamp == self.spinBox_recordLength.value()
        nprematch = npre == self.spinBox_pretrigLength.value()
        if not (nsmatch and nprematch):
            self.setPulseSync(Sync.UNKNOWN)

    def handleChooseProjectors(self):
        startdir = os.path.dirname(self.lineEdit_projectors.text())
        if not os.path.isdir(startdir):
            startdir = os.path.expanduser("~")
        fileName = projectors.getFileNameWithDialog(self, startdir)
        if fileName:
            self.lineEdit_projectors.setText(fileName)

    def handleSendProjectors(self):
        fileName = self.lineEdit_projectors.text()
        success = projectors.sendProjectors(
            self, fileName, self.dcom.channel_names, self.client
        )
        print(f"sendprojectors success success = {success}")
        if success:
            self.settings.setValue("projectors_file", self.lineEdit_projectors.text())
            self.setProjectorSync(True)
        return success
