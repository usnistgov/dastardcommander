import numpy as np
import os
from matplotlib import cm
import time
from string import ascii_uppercase
import itertools

# Qt5 imports
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot, pyqtSignal
import PyQt5.uic


def iter_all_strings():
    "Iterator that returns A,B,C,...X,Y,Z,AA,AB,...ZX,ZY,ZZ,AAA,AAB,..."
    # From Stack Overflow. See https://bit.ly/2pJS6kN
    size = 1
    while True:
        for s in itertools.product(ascii_uppercase, repeat=size):
            yield "".join(s)
        size += 1


class ExperimentStateIncrementer:
    def __init__(self, newStateButton, ignoreButton, label, parent):
        self.newStateButton = newStateButton
        self.ignoreButton = ignoreButton
        self.ignoring = False
        self.label = label
        self.parent = parent
        self.newStateButton.clicked.connect(self.handleNewStateButton)
        self.ignoreButton.clicked.connect(self.handleIgnoreButton)
        self.resetStateLabels()
        self.updateLabel("???? unknown state")

    def nextLabel(self):
        # first call returns "A", succesive calls return "B","C",...,"AA","AB",...,"BA","BB" on so on
        for s in self._gen:
            return s

    def updateLabel(self, stateName):
        self.label.setText(
            "Current State: {} at {}".format(stateName, time.strftime("%H:%M:%S on %a"))
        )

    def handleNewStateButton(self):
        self.sendState(self.nextLabel())

    def sendState(self, stateName):
        config = {
            "Label": stateName,
            "WaitForError": True,
        }
        _, err = self.parent.client.call(
            "SourceControl.SetExperimentStateLabel", config
        )
        if err:
            return
        self.updateLabel(stateName)
        self.ignoring = stateName == "IGNORE"
        if self.ignoring:
            self.ignoreButton.setText('Restart state "%s"' % self.lastValidState)
        else:
            self.lastValidState = stateName
            self.ignoreButton.setText("Set state IGNORE")

    def handleIgnoreButton(self):
        """IGNORE button behavior depends on self.ignoring.
        If we're in a valid mode (self.ignoring is False), then switch state to IGNORE.
        Otherwise, switch back to the last valid state."""
        if self.ignoring:
            self.sendState(self.lastValidState)
        else:
            self.sendState("IGNORE")

    def resetStateLabels(self):
        self._gen = iter_all_strings()
        self.updateLabel("START")
        self.lastValidState = "START"


class Observe(QtWidgets.QWidget):
    """The tricky bit about this widget is that it cannot be properly set up until
    dc has processed both a CHANNELNAMES message and a STATUS message (to get the
    number of rows and columns)."""

    def __init__(self, parent, host, client):
        QtWidgets.QWidget.__init__(self, parent)
        self.client = client
        self.host = host
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/observe.ui"), self)
        self.pushButton_resetIntegration.clicked.connect(self.resetIntegration)
        self.pushButton_autoScale.clicked.connect(self.handleAutoScaleClicked)
        self.mapLoadButton.clicked.connect(self.handleLoadMap)
        self.crm_grid = None
        self.crm_map = None
        self.countsSeens = []
        self.ngroups = 0
        self.chan_per_group = []
        self.channel_names = []  # injected from dc.py
        self.auxPerChan = 0
        self.lastTotalRate = 0
        self.mapfile = ""
        self.ExperimentStateIncrementer = ExperimentStateIncrementer(
            self.pushButton_experimentStateNew,
            self.pushButton_experimentStateIGNORE,
            self.label_experimentState,
            self,
        )

    blocklist_changed = pyqtSignal()
    block_channel = pyqtSignal(int)

    def handleTriggerRateMessage(self, d):
        if self.ngroups == 0:
            print("Ignoring trigger rate message that arrived before array status")
            return
        if len(self.channel_names) == 0:
            print("Ignoring trigger rate message that arrived before channel names")
            return
        if self.crm_grid is None:
            self.buildCRM()

        countsSeen = np.array(d["CountsSeen"])
        integrationTime = self.spinBox_integrationTime.value()
        self.countsSeens.append(countsSeen)
        n = min(len(self.countsSeens), integrationTime)
        self.countsSeens = self.countsSeens[-n:]
        countRates = np.zeros(len(countsSeen))
        for cs in self.countsSeens:
            countRates += cs
        countRates /= len(self.countsSeens)
        colorScale = self.getColorScale(countRates)
        if self.crm_grid is not None:
            self.crm_grid.setCountRates(countRates, colorScale)
        if hasattr(self, "pixelMap"):
            if self.crm_map is None or len(self.crm_map.buttons) == 0:
                # if we build the crm_map before we know the source and know channel_names
                # (eg before a dastard source is started) we will need to rebuild it later
                # so we check here
                print("rebuding CRMMap due to len(buttons)==0")
                self.buildCRMMap()
                print("now have len(buttons)={}".format(len(self.crm_map.buttons)))
            self.crm_map.setCountRates(countRates, colorScale)
        integrationComplete = len(self.countsSeens) == integrationTime
        arrayCps = 0
        auxCps = 0
        for cr, channel_name in zip(countRates, self.channel_names):
            if channel_name.startswith("chan"):
                arrayCps += cr
            else:
                auxCps += cr
        self.setArrayCps(arrayCps, integrationComplete, auxCps)

    def getColorScale(self, countRates):
        if self.pushButton_autoScale.isChecked():
            totalRate = countRates.sum()
            # Be careful not to have divide-by-zero error here.
            fracDiff = 0.0
            denom = self.lastTotalRate + totalRate
            if denom > 0:
                fracDiff = np.abs(self.lastTotalRate - totalRate) / denom
            self.lastTotalRate = totalRate
            if fracDiff > 0.2:
                maxRate = np.amax(countRates)
                self.doubleSpinBox_colorScale.setValue(maxRate)
        return self.doubleSpinBox_colorScale.value()

    def setArrayCps(self, arrayCps, integrationComplete, auxCps):
        s = "{:.2f} cps/array".format(arrayCps)
        self.label_arrayCps.setText(s)
        self.label_arrayCps.setEnabled(integrationComplete)
        sAux = "{:.2f} aux cps".format(auxCps)
        self.label_auxCps.setText(sAux)

    def buildCRM(self):
        self.deleteCRMGrid()
        self.crm_grid = CountRateMap(self, self.ngroups, self.chan_per_group, self.channel_names)
        self.gridScrollLayout.addWidget(self.crm_grid)

        # Remove the prior colorbar (or the Horizontal Spacer, if this is the first call)
        prevCB = self.colorbarLayout.itemAt(1)
        self.colorbarLayout.removeItem(prevCB)
        self.colorbarLayout.insertWidget(1, self.crm_grid.colorbar)

    def deleteCRMGrid(self):
        if self.crm_grid is not None:
            self.crm_grid.parent = None
            self.crm_grid.deleteLater()
            self.crm_grid = None

    def buildCRMMap(self):
        self.deleteCRMMap()
        print(f"Building CountRateMap with {self.ngroups} channel groups")
        print(f"There are {len(self.channel_names)} channel names.")
        self.crm_map = CountRateMap(
            self, self.ngroups, self.chan_per_group, self.channel_names, xy=self.pixelMap
        )
        # if we build the crm_map before we know the source and know channel_names
        # (eg before a dastard source is started) we will need to rebuild it later
        self.MapTab.layout().addWidget(self.crm_map, 0)

    def deleteCRMMap(self):
        if self.crm_map is not None:
            self.crm_map.parent = None
            self.crm_map.deleteLater()
            self.crm_map = None

    def handleStatusUpdate(self, is_running, source_name, groups_info):
        if not is_running:
            return self.handleStop()
        ngroup = len(groups_info)
        self.ngroups = ngroup
        self.chan_per_group = [v["Nchan"] for v in groups_info]
        self.deleteCRMGrid()
        self.deleteCRMMap()

    def handleStop(self):
        self.ngroups = 0
        self.chan_per_group = []
        self.deleteCRMGrid()
        self.deleteCRMMap()

    @pyqtSlot()
    def resetIntegration(self):
        self.countsSeens = []
        if self.crm_grid is not None:
            self.crm_grid.setCountRates(np.zeros(len(self.crm_grid.buttons)), 1)
        self.setArrayCps(0, False, 0)

    @pyqtSlot()
    def pushedClearDisabled(self):
        """GUI requested the disabled list be cleared."""
        for map in (self.crm_grid, self.crm_map):
            if map is None:
                continue
            map.enableAllChannels()

    def handleAutoScaleClicked(self):
        self.doubleSpinBox_colorScale.setEnabled(
            not self.pushButton_autoScale.isChecked()
        )
        self.lastTotalRate = 0  # make sure auto scale actually happens

    def handleLoadMap(self):
        if self.host == "localhost":
            file, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select a TES map file", self.mapfile, "Maps (*.cfg *.txt)"
            )
            if file == "":
                return
        else:
            file, okay = QtWidgets.QInputDialog.getText(
                self,
                "Choose map file",
                "Enter full path to map file on %s (remote server):" % self.host,
                QtWidgets.QLineEdit.Normal,
                self.mapfile,
            )
            if not okay or file == "":
                return
        okay = self.client.call("MapServer.Load", file)

    def handleTESMapFile(self, filename):
        self.mapfile = filename
        head, tail = os.path.split(filename)
        self.mapFileLabel.setText("Map File: %s" % tail)

    def handleTESMap(self, msg):
        scale = 1.0 / float(msg["Spacing"])
        minx = np.min([p["X"] for p in msg["Pixels"]])
        maxy = np.max([p["Y"] for p in msg["Pixels"]])
        print("MinX = ", minx, " MaxY=", maxy)
        self.pixelMap = [
            ((p["X"] - minx) * scale, (maxy - p["Y"]) * scale) for p in msg["Pixels"]
        ]
        print("handleTESMap with spacing ", msg["Spacing"], " scale ", scale)
        self.buildCRMMap()

    def handleExternalTriggerMessage(self, msg):
        n = msg["NumberObservedInLastSecond"]
        self.label_externalTriggersInLastSecond.setText(
            "{} external triggers in last second".format(n)
        )

    def handleWritingMessage(self, msg):
        if msg["Active"]:
            print("Observe got Writing Active=True message, resetting state labels")
            self.ExperimentStateIncrementer.resetStateLabels()


class CountRateColorBar(QtWidgets.QWidget):
     "Show the event rate color scale as a color bar"
     def paintEvent(self, event):
         qp = QtGui.QPainter(self)
         qp.setPen(QtCore.Qt.NoPen)
         size = self.size()
         w = size.width()
         h = size.height()

         Nboxes = max(50, w//2)
         for i in range(Nboxes):
             f = float(i)/Nboxes
             color = self.cmap(f, bytes=True)
             qp.setBrush(QtGui.QColor(*color))
             qp.drawRect(int(f*w+0.5), 0, int(float(w)/Nboxes)+1, int(h*1.0))

_QT_DEFAULT_FONT = ""  # This is the easiest way to specify the default font


class CountRateMap(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""

    enabledFont = QtGui.QFont(_QT_DEFAULT_FONT, 8, QtGui.QFont.Bold)
    disabledFont = QtGui.QFont(_QT_DEFAULT_FONT, 8, QtGui.QFont.Bold)
    enabledForeground = "black"
    disabledForeground = "white"
    disabledColor = "black"
    cmap = cm.get_cmap("Wistia")
    cmap_disabled = cm.get_cmap("hot")

    def __init__(self, parent, ngroups, chan_per_group, channel_names, xy=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.owner = parent
        self.buttons = []
        self.named_buttons = {}
        self.ngroups = ngroups
        self.chan_per_group = chan_per_group
        self.channel_names = channel_names
        self.triggerBlocker = parent.triggerBlocker
        if xy is None:
            scale=24
            self.initButtons(scale=scale)
        else:
            scale=24
            self.initButtons(scale=scale, xy=xy)

        self.colorbar = CountRateColorBar(self)
        # self.colorbar.move(0, int((self.ngroups+0.5)*scale))
        w = parent.width()
        self.colorbar.resize(w, scale)
        self.colorbar.cmap = self.cmap

    def addButton(self, x, y, xwidth, ywidth, name, tooltip):
        button = QtWidgets.QPushButton(self)
        button.move(x, y)
        button.setFixedSize(xwidth, ywidth)
        button.setFont(self.enabledFont)
        button.setFlat(False)
        button.chanName = name
        button.chanIndex = len(self.buttons)
        button.chanNumber = None
        button.clicked.connect(lambda: self.click_callback(button))
        button.setToolTip(tooltip)
        button.triggers_blocked = False
        self.buttons.append(button)
        self.named_buttons[name] = button
        try:
            chnum = int(name.replace("chan", ""))
            button.chanNumber = chnum
            if chnum in self.triggerBlocker.blocked:
                self.setButtonDisabled(name)
        except ValueError:
            pass

    @pyqtSlot()
    def click_callback(self, button):
        name = button.chanName
        cnum = button.chanNumber
        self.triggerBlocker.toggle_channel(cnum)
        if cnum in self.triggerBlocker.blocked:
            print(f"Channel {name} triggering is disabled.")
            self.setButtonDisabled(name)
            self.owner.block_channel.emit(button.chanIndex)
        else:
            print(f"Channel {name} triggering is enabled.")
            self.setButtonEnabled(name)
        self.owner.blocklist_changed.emit()

    def setButtonDisabled(self, name):
        button = self.named_buttons.get(name, None)
        if button is None:
            return
        button.triggers_blocked = True
        button.setFont(self.disabledFont)
        button.setText("X")
        colorString = (
            f"QPushButton {{color: {self.disabledForeground}; background-color : {self.disabledColor};}}"
        )
        button.setStyleSheet(colorString)
        tt = button.toolTip()
        if "DISABLED" not in tt:
            tt = "[DISABLED] " + tt
            button.setToolTip(tt)

    def setButtonEnabled(self, name):
        button = self.named_buttons.get(name, None)
        if button is None:
            return
        button.triggers_blocked = False
        button.setFont(self.enabledFont)
        button.setText("--")
        colorString = f"QPushButton {{color: {self.enabledForeground}; background-color : white;}}"
        button.setStyleSheet(colorString)
        tt = button.toolTip()
        if "DISABLED" in tt:
            tt = tt.replace("[DISABLED] ", "")
            button.setToolTip(tt)

    def enableAllChannels(self):
        """The list of blocked channels has been cleared. Enable all GUI elements."""
        for (name, button) in self.named_buttons.items():
            if button.triggers_blocked:
                self.setButtonEnabled(name)

    def deleteButtons(self):
        for button in self.buttons:
            if button is None:
                continue
            button.setParent(None)
            button.deleteLater()
        self.buttons = []

    def setColsRows(self, ngroups, chan_per_group):
        if ngroups != self.ngroups or len(chan_per_group) != len(self.chan_per_group):
            self.ngroups = ngroups
            self.chan_per_group = chan_per_group
            self.initButtons()

    def initButtons(self, scale=25, xy=None):
        MaxPerRow = 32  # no more than this many buttons per row
        self.deleteButtons()
        horizdisp = chnum = vertdisp = groupnum = i = 0
        wrappedrows = np.any([n > MaxPerRow for n in self.chan_per_group])
        # groupnum means the TES's group number (actual column number in TDM)
        # chnum means TES's channel number within the group (actual row number in TDM)

        for name in self.channel_names:
            # No count rate buttons for Lancero error channels, or any others not called "chan*"
            if not name.startswith("chan"):
                self.buttons.append(None)
                continue
            if xy is None:
                x = scale * horizdisp
                y = scale * vertdisp
                if wrappedrows:
                    y += int(0.4*scale*groupnum)
            else:
                x = scale * xy[i][0]
                y = scale * xy[i][1]
            tooltip = "{}, ({} of grp {})".format(name, chnum, groupnum)
            self.addButton(x, y, scale - 1, scale - 1, name, tooltip)
            horizdisp += 1
            chnum += 1
            i += 1
            if chnum >= self.chan_per_group[groupnum]:
                chnum = horizdisp = 0
                vertdisp += 1
                groupnum += 1
            elif horizdisp >= MaxPerRow:
                horizdisp = 0
                vertdisp += 1

    def setCountRates(self, countRates, colorScale):
        colorScale = float(colorScale)
        self.owner.maxRateLabel.setText("Max rate: {:.2f}/sec".format(colorScale))
        assert len(countRates) == len(self.buttons)
        for i, cr in enumerate(countRates):
            button = self.buttons[i]
            if button is None:
                continue
            if cr < 10:
                buttonText = "{:.2f}".format(cr)
            elif cr < 100:
                buttonText = "{:.1f}".format(cr)
            else:
                buttonText = "{:.0f}".format(cr)
            button.setText(buttonText)

            if button.triggers_blocked:
                textcolor = self.disabledForeground
                scaledrate = min(0.5*cr/colorScale, 1)
                bgcolor = self.cmap_disabled(scaledrate, bytes=True)
            else:
                textcolor = self.enabledForeground
                bgcolor = self.cmap(cr / colorScale, bytes=True)
            colorString = "rgb({},{},{})".format(bgcolor[0], bgcolor[1], bgcolor[2])
            colorString = f"QPushButton {{color: {textcolor}; background-color: {colorString};}}"
            button.setStyleSheet(colorString)
