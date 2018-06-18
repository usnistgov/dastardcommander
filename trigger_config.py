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
        self.trigger_state = {}

    def handleTriggerMessage(self, dicts):
        """Handle the trigger state message (in list-of-dicts form)"""
        for d in dicts:
            for ch in d["ChanNumbers"]:
                self.trigger_state[ch] = d
        print "Trigger state:\n", self.trigger_state

    def channelChooserChanged(self):
        """The channel selector menu was activated: update the edit box"""
        cctext = self.ui.channelChooserBox.currentText()
        if cctext.startswith("All"):
            allprefixes = [self.chanbyprefix(p) for p in self.channel_prefixes]
            allprefixes.sort()
            result = "\n".join(allprefixes)
        elif cctext.startswith("user"):
            return
        else:
            prefix = cctext.split()[0].lower()
            if prefix == "FB":
                prefix = "ch"
            result = self.chanbyprefix(prefix)
        self.ui.channelsChosenEdit.setPlainText(result)

    def chanbyprefix(self, prefix):
        """Return a string listing all channels for the given prefix"""
        cnum = ",".join([p.lstrip(prefix) for p in self.channel_names if p.startswith(prefix)])
        return "%s:%s" % (prefix, cnum)

    def channelListTextChanged(self):
        """The channel selector text edit box changed."""
        self.parseChannelText()
        self.updateTriggerStatus()

    def parseChannelText(self):
        """Parse the text in the channel selector text edit box. Set the list
        self.chosenChannels accordingly."""
        self.chosenChannels = []
        chantext = self.ui.channelsChosenEdit.toPlainText()
        print ("Trying to update the channel information")
        chantext = chantext.replace("\t", "\n").replace(";", "\n").replace(" ", "")
        lines = chantext.split()
        for line in lines:
            if not ":" in line:
                continue
            prefix, cnums = line.split(":", 1)
            if prefix not in self.channel_prefixes:
                print("Channel prefix %s not in known prefixes: %s"%(prefix, self.channel_prefixes))
                continue
            for cnum in cnums.split(","):
                name = prefix+cnum
                try:
                    idx = self.channel_names.index(name)
                    self.chosenChannels.append(idx)
                except ValueError:
                    print ("Channel %s not known" % (name))
        print "The chosen channels are ", self.chosenChannels

    def getstate(self, name):
        channels = self.chosenChannels
        for ch in channels:
            if ch not in self.trigger_state:
                return None
        x = self.trigger_state[channels[0]].get(name, None)
        if x is None:
            return None
        for ch in channels[1:]:
            y = self.trigger_state[ch].get(name, None)
            if x != y:
                return None
        return x

    def updateTriggerStatus(self):
        """Given the self.chosenChannels, update the various trigger status GUI elements."""

        boxes = (
            (self.ui.autoTrigActive, "AutoTrigger"),
            (self.ui.edgeTrigActive, "EdgeTrigger"),
            (self.ui.levelTrigActive, "LevelTrigger"),
            (self.ui.noiseTrigActive, "NoiseTrigger"),
        )
        for (checkbox, name) in boxes:
            state = self.getstate(name)
            checkbox.setTristate(state is None)
            if state is not None:
                checkbox.setChecked(state)

        levelscale = edgescale = 1.0
        if self.ui.levelVoltsRaw.currentText().startswith("Volts"):
            levelscale = 1./16384.0
            edgescale = levelscale * 100  # TODO: replace 100 with samples per second
        edits = (
            (self.ui.autoTimeEdit, "AutoDelay", 1e-6),
            (self.ui.edgeEdit, "EdgeLevel", edgescale),
            (self.ui.levelEdit, "LevelLevel", levelscale),
            # (self.ui.noiseEdit, "NoiseLevel", 1.0)
        )
        for (edit, name, scale) in edits:
            state = self.getstate(name)
            if state is None:
                edit.setText("")
                continue
            edit.setText("%f" % (state*scale))

        r = self.getstate("EdgeRising")
        f = self.getstate("EdgeFalling")
        if r and f:
            self.ui.edgeRiseFallBoth.setCurrentIndex(2)
        elif f:
            self.ui.edgeRiseFallBoth.setCurrentIndex(1)
        else:
            self.ui.edgeRiseFallBoth.setCurrentIndex(0)

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
        """Changed the edge+level units between RAW and Volts"""
        self.updateTriggerStatus()

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
        print "Here we tell the server records are %d (%d pretrigger)" % (samp, presamp)
        self.client.call("SourceControl.ConfigurePulseLengths", {"Nsamp": samp, "Npre": presamp})
