# Qt5 imports
import PyQt5.uic
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt

# other non qt imports
import os


class TriggerConfig(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""

    changedTriggerStateSig = pyqtSignal()

    def __init__(self, parent, client):
        QtWidgets.QWidget.__init__(self, parent)
        self.client = client
        PyQt5.uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui/trigger_config.ui"), self
        )
        self.recordLengthSpinBox.editingFinished.connect(self.sendRecordLengthsToServer)
        self.pretrigLengthSpinBox.editingFinished.connect(
            self.sendRecordLengthsToServer
        )
        self.pretrigPercentSpinBox.editingFinished.connect(
            self.sendRecordLengthsToServer
        )
        self.channelsChosenEdit.textChanged.connect(self.channelListTextChanged)
        self.auto1psModeButton.clicked.connect(self.go1psMode)
        self.noiseModeButton.clicked.connect(self.goNoiseMode)
        self.pulseModeButton.clicked.connect(self.goPulseMode)
        self.groupTriggerClearAll.clicked.connect(self.pushedClearGroupTrigger)
        self.groupTriggerAdd.clicked.connect(self.pushedAddGroupTrigger)
        self.groupTriggerRemove.clicked.connect(self.pushedRemoveGroupTrigger)
        self.trigger_state = {}
        self.chosenChannels = []
        self.editWidgets = [
            self.recordLengthSpinBox,
            self.pretrigLengthSpinBox,
            self.pretrigPercentSpinBox,
            self.autoTimeEdit,
            self.levelEdit,
            self.edgeEdit,
        ]
        # Initialize these two to a value that definitly won't match next value
        self.lastPretrigLength = -1
        self.lastRecordLength = -1
        # self.channel_names has been set to equal the same list belonging to the main window

    def _closing(self):
        """The main window calls this to block any editingFinished events from
        being processed when the main window is closing."""
        for w in self.editWidgets:
            w.blockSignals(True)

    def isTDM(self, tdm):
        combo = self.channelChooserBox
        if tdm:
            if combo.count() == 2:
                combo.addItem("Signal channels")
                combo.addItem("TDM error channels")
            combo.setCurrentIndex(2)
        else:
            while combo.count() > 2:
                combo.removeItem(2)
            combo.setCurrentIndex(1)

    @pyqtSlot()
    def goPulseMode(self):
        self.autoTrigActive.setChecked(False)
        self.edgeTrigActive.setChecked(True)
        self.levelTrigActive.setChecked(False)
        self.changedAllTrigConfig()

    @pyqtSlot()
    def goNoiseMode(self):
        self.autoTrigActive.setChecked(True)
        self.autoTimeEdit.setText("0")
        self.edgeTrigActive.setChecked(False)
        self.levelTrigActive.setChecked(False)
        self.changedAllTrigConfig()

    @pyqtSlot()
    def go1psMode(self):
        self.autoTrigActive.setChecked(True)
        self.autoTimeEdit.setText("1000")
        self.edgeTrigActive.setChecked(False)
        self.levelTrigActive.setChecked(False)
        self.changedAllTrigConfig()

    def handleTriggerMessage(self, dicts):
        """Handle the trigger state message (in list-of-dicts form)"""
        for d in dicts:
            d["EdgeMulti"] = False  # ignore all EdgeMulti settings from the server
            # so that we don't send them back... avoid EdgeMulti being stuck on
            for channelIndex in d["ChannelIndices"]:
                self.trigger_state[channelIndex] = d
        self.updateTriggerGUIElements()
        self.changedTriggerStateSig.emit()

    @pyqtSlot()
    def channelChooserChanged(self):
        """The channel selector menu was activated: update the edit box"""
        idx = self.channelChooserBox.currentIndex()
        if idx < 0:
            return
        cctext = self.channelChooserBox.currentText()
        if cctext.startswith("All"):
            allprefixes = [self.chanbyprefix(p) for p in self.channel_prefixes]
            allprefixes.sort()
            result = "\n".join(allprefixes)
        elif cctext.startswith("user"):
            return
        else:
            prefix = cctext.split()[0]
            if prefix == "Signal":
                prefix = "chan"
            elif prefix == "TDM":
                prefix = "err"
            result = self.chanbyprefix(prefix)
        self.channelsChosenEdit.setPlainText(result)
        if idx != self.channelChooserBox.currentIndex():
            self.channelChooserBox.setCurrentIndex(idx)
        self.updateTriggerGUIElements()

    def chanbyprefix(self, prefix, include_blocked=False):
        """Return a string listing all channels for the given prefix"""
        unblocked_chan = []
        for p in self.channel_names:
            if p.startswith(prefix):
                num = p.lstrip(prefix)
                if int(num) not in self.triggerBlocker.blocked:
                    unblocked_chan.append(num)
        cnum = ",".join(unblocked_chan)
        return "%s:%s" % (prefix, cnum)

    @pyqtSlot()
    def channelListTextChanged(self):
        """The channel selector text edit box changed."""
        self.parseChannelText()
        self.updateTriggerGUIElements()

    def parseChannelText(self):
        """Parse the text in the channel selector text edit box. Set the list
        self.chosenChannels accordingly."""
        self.chosenChannels = []
        chantext = self.channelsChosenEdit.toPlainText()
        chantext = chantext.replace("\t", "\n").replace(";", "\n").replace(" ", "")
        lines = chantext.split()
        for line in lines:
            if ":" not in line:
                continue
            prefix, cnums = line.split(":", 1)
            if prefix not in self.channel_prefixes:
                print(
                    "Channel prefix %s not in known prefixes: %s"
                    % (prefix, self.channel_prefixes)
                )
                continue
            for cnum in cnums.split(","):
                # Ignore the "" that follows a trailing comma
                if len(cnum) == 0:
                    continue
                name = prefix + cnum
                try:
                    idx = self.channel_names.index(name)
                    self.chosenChannels.append(idx)
                except ValueError:
                    print("Channel '%s' is not known" % (name))
        self.channelChooserBox.setCurrentIndex(0)

    def getstate(self, name):
        "Get the self.trigger_state value named name. If mutiple values, return None"
        channels = self.chosenChannels
        if len(channels) == 0:
            return None
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

    def alltriggerstates(self):
        """Return all unique dictionaries that are values in the self.trigger_state dict.
        There might be 100s of entries in self.trigger_state dict but only one or a few
        unique values in it."""

        # A set() might seem natural but cannot be used to store unhashable items like dicts.
        allstates = []
        for ch in self.chosenChannels:
            # This will add a trigger state to the list only if it's not already in the list.
            if ch in self.trigger_state and self.trigger_state[ch] not in allstates:
                allstates.append(self.trigger_state[ch])

        # Now we need to split states if any of allstates refers to channels both
        # in AND out of self.chosenChannels. Those dictionaries each become 2 dictionaries.
        for state in allstates:
            chans = state["ChannelIndices"]
            keep = []
            splitoff = []
            for c in chans:
                if c in self.chosenChannels:
                    keep.append(c)
                else:
                    splitoff.append(c)
            if len(splitoff) > 0:
                state["ChannelIndices"] = keep
                for c in keep:
                    self.trigger_state[c] = state
                newstate = state.copy()
                newstate["ChannelIndices"] = splitoff
                for c in splitoff:
                    self.trigger_state[c] = newstate
        return allstates

    def configureDastardTriggers(self):
        for state in self.alltriggerstates():
            self.client.call("SourceControl.ConfigureTriggers", state)

    def setstates(self, newstate):
        "Set the self.trigger_state value named name to newvalue"
        for state in self.alltriggerstates():
            for name, val in newstate.items():
                state[name] = val

    def updateTriggerGUIElements(self):
        """Given the self.chosenChannels, update the various trigger status GUI elements."""

        boxes = (
            (self.autoTrigActive, "AutoTrigger"),
            (self.edgeTrigActive, "EdgeTrigger"),
            (self.levelTrigActive, "LevelTrigger"),
        )
        for (checkbox, name) in boxes:
            state = self.getstate(name)
            if state is None:
                checkbox.setTristate(True)
                checkbox.setCheckState(Qt.PartiallyChecked)
            else:
                checkbox.setTristate(False)
                checkbox.setChecked(state)

        levelscale = edgescale = 1.0
        if self.levelVoltsRaw.currentText().startswith("Volts"):
            levelscale = 1.0 / 16384.0
            edgescale = levelscale * 100  # TODO: replace 100 with samples per second
            self.levelUnitsLabel.setText("Volts")
            self.edgeUnitsLabel.setText("V/ms")
        else:
            self.levelUnitsLabel.setText("raw")
            self.edgeUnitsLabel.setText("raw/samp")
        edits = (
            (self.autoTimeEdit, "AutoDelay", 1e-6),
            (self.edgeEdit, "EdgeLevel", edgescale),
            (self.levelEdit, "LevelLevel", levelscale),
        )
        for (edit, name, scale) in edits:
            state = self.getstate(name)
            if state is None:
                edit.setText("")
                continue
            edit.setText("%f" % (state * scale))

        r = self.getstate("EdgeRising")
        f = self.getstate("EdgeFalling")
        if r and f:
            self.edgeRiseFallBoth.setCurrentIndex(2)
        elif f:
            self.edgeRiseFallBoth.setCurrentIndex(1)
        else:
            self.edgeRiseFallBoth.setCurrentIndex(0)

    @pyqtSlot()
    def pushedAddGroupTrigger(self):
        self.changeGroupTrigger(True)

    @pyqtSlot()
    def pushedRemoveGroupTrigger(self):
        self.changeGroupTrigger(False)

    def changeGroupTrigger(self, add):
        # Parse trigger list
        rx = self.groupTriggerReceivers.text()
        rxsplit = rx.replace(",", " ").split()  # split on comma and/or white space
        rx_channums = []
        for x in rxsplit:
            try:
                rx_channums.append(int(x))
            except ValueError:
                pass
        if len(rx_channums) == 0:
            me = "TriggerConfig.changeGroupTrigger"
            print("{}: Could not parse channel list '{}'".format(me, rx))
            return
        sourcenum = self.groupTriggerSource.value()
        state = {"Connections": {sourcenum: rx_channums}}
        request = "SourceControl.AddGroupTriggerCoupling"
        if not add:
            request = "SourceControl.DeleteGroupTriggerCoupling"
        self.client.call(request, state)

    @pyqtSlot()
    def pushedClearGroupTrigger(self):
        self.coupleFBToErrCheckBox.setChecked(False)
        self.coupleErrToFBCheckBox.setChecked(False)
        text = "Active group trigger sources: <none>"
        self.groupTriggerActiveSrc.setText(text)
        self.groupTriggerActiveRx.setText(text)
        dummy = True
        self.client.call("SourceControl.StopTriggerCoupling", dummy)

    @pyqtSlot()
    def pushedClearDisabled(self):
        changed = self.triggerBlocker.clear()
        assert len(self.triggerBlocker.blocked) == 0
        if changed:
            self.updateDisabledList()

    @pyqtSlot()
    def updateDisabledList(self):
        ndisabled = len(self.triggerBlocker.blocked)
        if ndisabled == 0:
            msg = "All channels are enabled"
        elif ndisabled == 1:
            msg = "One channel is disabled: {}".format(self.triggerBlocker.blocked[0])
        else:
            msg = "{} channels are disabled: {}".format(
                ndisabled, ",".join(map(str, self.triggerBlocker.blocked))
            )
        self.disabledTextEdit.setPlainText(msg)
        self.channelChooserChanged()  # update that text box

    @pyqtSlot(int)
    def blockTriggering(self, channelIndex):
        """Block all triggering from channel with index `channelIndex`."""
        self.trigger_state[channelIndex]["ChannelIndices"].remove(channelIndex)
        notrig_state = self.trigger_state[channelIndex].copy()
        self.trigger_state[channelIndex] = notrig_state
        notrig_state["ChannelIndices"] = [channelIndex]
        notrig_state["AutoTrigger"] = False
        notrig_state["EdgeTrigger"] = False
        notrig_state["LevelTrigger"] = False
        self.configureDastardTriggers()

    def handleGroupTriggerMessage(self, msg):
        """Handle the group trigger state message"""
        # Store sources and receivers in set objects to de-duplicate the numbering.
        # Do not store the complete set of src->rx connections, b/c there's no GUI
        # purpose to doing so at this time.
        allsrc, allrx = set(), set()
        conn = msg["Connections"]
        for src, rx in conn.items():
            allsrc.add(src)
            allrx.update(rx)

        # Update the two GUI labels that list the active sources and receivers
        for cnum_set, name, gui_label in zip(
            (allsrc, allrx),
            ("sources", "receivers"),
            (self.groupTriggerActiveSrc, self.groupTriggerActiveRx),
        ):
            cnum_text = "<none>"
            if len(cnum_set) > 0:
                cnumbers = list(cnum_set)
                cnumbers.sort()
                cnum_list = [str(x) for x in cnumbers]
                # Truncate a too-long list (replace last with ellipsis)
                if len(cnumbers) > 35:
                    cnum_list = cnum_list[:35]
                    cnum_list[-1] = "..."
                cnum_text = "[{:}]".format(",".join(cnum_list))
            text = "Active group trigger {}: {}".format(name, cnum_text)
            gui_label.setText(text)

    @pyqtSlot()
    def checkedCoupleFBErr(self):
        on = self.coupleFBToErrCheckBox.isChecked()
        if on:
            self.coupleErrToFBCheckBox.setChecked(False)
        self.client.call("SourceControl.CoupleFBToErr", on)

    @pyqtSlot()
    def checkedCoupleErrFB(self):
        on = self.coupleErrToFBCheckBox.isChecked()
        if on:
            self.coupleFBToErrCheckBox.setChecked(False)
        self.client.call("SourceControl.CoupleErrToFB", on)

    def handleTrigCoupling(self, msg):
        fberr = errfb = False
        if msg == 2:
            fberr = True
        elif msg == 3:
            errfb = True
        elif msg != 1:
            print("message: TRIGCOUPLING {}, but expect 1, 2 or 3".format(msg))
        self.coupleFBToErrCheckBox.setChecked(fberr)
        self.coupleErrToFBCheckBox.setChecked(errfb)

    def changedAllTrigConfig(self):
        "Update all trigger config GUI elements for new configuration"
        self.changedAutoTrigConfig()
        self.changedEdgeTrigConfig()
        self.changedLevelTrigConfig()

    @pyqtSlot()
    def changedAutoTrigConfig(self):
        newstate = {}
        auto = self.autoTrigActive.checkState()
        if not auto == Qt.PartiallyChecked:
            self.autoTrigActive.setTristate(False)
            newstate["AutoTrigger"] = auto == Qt.Checked

        delay = self.autoTimeEdit.text()
        try:
            nsdelay = int(round(float(delay) * 1e6))
            newstate["AutoDelay"] = nsdelay
        except ValueError:
            pass
        self.setstates(newstate)
        self.configureDastardTriggers()

    @pyqtSlot()
    def changedEdgeTrigConfig(self):
        newstate = {}
        edge = self.edgeTrigActive.checkState()
        if not edge == Qt.PartiallyChecked:
            self.edgeTrigActive.setTristate(False)
            newstate["EdgeTrigger"] = edge == Qt.Checked
        rfb = self.edgeRiseFallBoth.currentText()
        if rfb.startswith("Rising"):
            newstate["EdgeRising"] = True
            newstate["EdgeFalling"] = False
        elif rfb.startswith("Falling"):
            newstate["EdgeRising"] = False
            newstate["EdgeFalling"] = True
        elif rfb.startswith("Either"):
            newstate["EdgeRising"] = True
            newstate["EdgeFalling"] = True

        edgeraw = self.edgeEdit.text()
        edgescale = 1.0
        if self.levelVoltsRaw.currentText().startswith("Volts"):
            edgescale = 1.0 / 16384.0
            # TODO: convert samples to ms
        try:
            edgeraw = int(float(edgeraw) / edgescale + 0.5)
            newstate["EdgeLeveL"] = edgeraw
        except ValueError:
            pass
        self.setstates(newstate)
        self.configureDastardTriggers()

    @pyqtSlot()
    def changedLevelTrigConfig(self):
        newstate = {}
        level = self.levelTrigActive.checkState()
        if not level == Qt.PartiallyChecked:
            self.levelTrigActive.setTristate(False)
            newstate["LevelTrigger"] = level == Qt.Checked
        rfb = self.levelRiseFallBoth.currentText()
        if rfb.startswith("Rising"):
            newstate["LevelRising"] = True
            newstate["LevelFalling"] = False
        elif rfb.startswith("Falling"):
            newstate["LevelRising"] = False
            newstate["LevelFalling"] = True
        elif rfb.startswith("Either"):
            newstate["LevelRising"] = True
            newstate["LevelFalling"] = True

        levelraw = self.levelEdit.text()
        levelscale = 1.0
        if self.levelVoltsRaw.currentText().startswith("Volts"):
            levelscale = 1.0 / 16384.0
        try:
            levelraw = int(float(levelraw) / levelscale + 0.5)
            newstate["LevelLevel"] = levelraw
        except ValueError:
            pass
        self.setstates(newstate)
        self.configureDastardTriggers()

    @pyqtSlot()
    def changedLevelUnits(self):
        """Changed the edge+level units between RAW and Volts"""
        self.updateTriggerGUIElements()

    @pyqtSlot(int, int)
    def updateRecordLengthsFromServer(self, nsamp, npre):
        samples = self.recordLengthSpinBox
        if samples.value() != nsamp:
            samples.setValue(nsamp)
            self.lastRecordLength = nsamp
        pretrig = self.pretrigLengthSpinBox
        if pretrig.value() != npre:
            pretrig.setValue(npre)
            self.lastPretrigLength = npre

    @pyqtSlot(int)
    def changedRecordLength(self, reclen):
        pretrig = self.pretrigLengthSpinBox
        pct = self.pretrigPercentSpinBox
        old_pt = pretrig.value()
        new_pt = int(0.5 + reclen * pct.value() / 100.0)
        if old_pt != new_pt:
            pretrig.valueChanged.disconnect()
            pretrig.setValue(new_pt)
            pretrig.valueChanged.connect(self.editedPretrigLength)

    @pyqtSlot()
    def editedPretrigLength(self):
        samples = self.recordLengthSpinBox
        pretrig = self.pretrigLengthSpinBox
        pct = self.pretrigPercentSpinBox
        pct.blockSignals(True)
        pct.setValue(pretrig.value() * 100.0 / samples.value())
        pct.blockSignals(False)

    @pyqtSlot()
    def editedPretrigPercentage(self):
        samples = self.recordLengthSpinBox
        pretrig = self.pretrigLengthSpinBox
        pct = self.pretrigPercentSpinBox
        pretrig.blockSignals(True)
        pretrig.setValue(int(0.5 + samples.value() * pct.value() / 100.0))
        pretrig.blockSignals(False)

    @pyqtSlot()
    def sendRecordLengthsToServer(self):
        samp = self.recordLengthSpinBox.value()
        presamp = self.pretrigLengthSpinBox.value()
        # Send a message to server only if one is changed
        if samp != self.lastRecordLength or presamp != self.lastPretrigLength:
            self.lastRecordLength = samp
            self.lastPretrigLength = presamp
            self.client.call(
                "SourceControl.ConfigurePulseLengths", {"Nsamp": samp, "Npre": presamp}
            )
