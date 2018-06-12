# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal

Ui_Trigger, _ = PyQt5.uic.loadUiType("triggerconfig.ui")


class TriggerConfig(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_Trigger()
        self.ui.setupUi(self)
        self.ui.recordLengthSpinBox.editingFinished.connect(self.sendRecordLengthsToServer)
        self.ui.pretrigLengthSpinBox.editingFinished.connect(self.sendRecordLengthsToServer)
        self.ui.pretrigPercentSpinBox.editingFinished.connect(self.sendRecordLengthsToServer)
        self.ui.channelsChosenEdit.textChanged.connect(self.channelListTextChanged)

    def channelChooserChanged(self):
        print("Channel Chooser menu new value: ", self.ui.channelChooserBox.currentText())

    def channelListTextChanged(self):
        print("Trying to update the channel information")

    def checkedCoupleFBErr(self):
        pass

    def checkedCoupleErrFB(self):
        pass

    def changedAutoTrigConfig(self):
        pass

    def changedEdgeTrigConfig(self):
        pass

    def changedLevelTrigConfig(self):
        pass

    def changedNoiseTrigConfig(self):
        pass
    def changedLevelUnits(self):
        pass

    def updateRecordLengthsFromServer(self, nsamp, npre):
        samples = self.ui.recordLengthSpinBox
        if samples.value() != nsamp:
            samples.setValue(nsamp)
        pretrig = self.ui.pretrigLengthSpinBox
        if pretrig.value() != npre:
            pretrig.setValue(npre)

    def changedRecordLength(self, reclen):
        pretrig = self.ui.pretrigLengthSpinBox
        pct = self.ui.pretrigPercentSpinBox
        old_pt = pretrig.value()
        new_pt = int(0.5+reclen*pct.value()/100.0)
        if old_pt != new_pt:
            pretrig.valueChanged.disconnect()
            pretrig.setValue(new_pt)
            pretrig.valueChanged.connect(self.editedPretrigLength)

    def editedPretrigLength(self):
        samples = self.ui.recordLengthSpinBox
        pretrig = self.ui.pretrigLengthSpinBox
        pct = self.ui.pretrigPercentSpinBox
        pct.blockSignals(True)
        pct.setValue(pretrig.value()*100.0/samples.value())
        pct.blockSignals(False)

    def editedPretrigPercentage(self):
        samples = self.ui.recordLengthSpinBox
        pretrig = self.ui.pretrigLengthSpinBox
        pct = self.ui.pretrigPercentSpinBox
        pretrig.blockSignals(True)
        pretrig.setValue(int(0.5+samples.value()*pct.value()/100.0))
        pretrig.blockSignals(False)

    def sendRecordLengthsToServer(self):
        samp = self.ui.recordLengthSpinBox.value()
        presamp = self.ui.pretrigLengthSpinBox.value()
        print "Here we tell the server records are %d (%d pretrigger)"%(samp, presamp)
        self.client.call("SourceControl.ConfigurePulseLengths", {"Nsamp":samp, "Npre":presamp})
