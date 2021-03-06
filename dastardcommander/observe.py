import numpy as np
import os
from matplotlib import cm
import time
from string import ascii_uppercase
import itertools

# Qt5 imports
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import pyqtSlot
import PyQt5.uic


def iter_all_strings():
    "Iterator that returns A,B,C,...X,Y,Z,AA,AB,...ZX,ZY,ZZ,AAA,AAB,..."
    # From Stack Overflow. See https://bit.ly/2pJS6kN
    size = 1
    while True:
        for s in itertools.product(ascii_uppercase, repeat=size):
            yield "".join(s)
        size += 1


class ExperimentStateIncrementer():
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
        self.label.setText("Current State: {} at {}".format(
            stateName,
            time.strftime("%H:%M:%S on %a")
        ))

    def handleNewStateButton(self):
        self.sendState(self.nextLabel())

    def sendState(self, stateName):
        config = {
            "Label": stateName,
            "WaitForError": True,
        }
        _, err = self.parent.client.call("SourceControl.SetExperimentStateLabel", config)
        if err:
            return
        self.updateLabel(stateName)
        self.ignoring = (stateName == "IGNORE")
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
        self.cols = 0
        self.rows = 0
        self.channel_names = []  # injected from dc.py
        self.auxPerChan = 0
        self.lastTotalRate = 0
        self.mapfile = ""
        self.ExperimentStateIncrementer = ExperimentStateIncrementer(
            self.pushButton_experimentStateNew,
            self.pushButton_experimentStateIGNORE, self.label_experimentState, self)

    def handleTriggerRateMessage(self, d):
        if self.cols == 0 or self.rows == 0:
            print("got trigger rate message before status")
            return
        if len(self.channel_names) == 0:
            print("got trigger rate message before channel names")
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
                fracDiff = np.abs(self.lastTotalRate-totalRate)/denom
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
        self.crm_grid = CountRateMap(self, self.cols, self.rows, self.channel_names)
        self.GridTab.layout().addWidget(self.crm_grid)

    def deleteCRMGrid(self):
        if self.crm_grid is not None:
            self.crm_grid.parent = None
            self.crm_grid.deleteLater()
            self.crm_grid = None

    def buildCRMMap(self):
        self.deleteCRMMap()
        print ("Building CountRateMap with %d cols x %d rows" % (self.cols, self.rows))
        print("len(channel_names", len(self.channel_names))
        self.crm_map = CountRateMap(self, self.cols, self.rows, self.channel_names,
                                    xy=self.pixelMap)
        # if we build the crm_map before we know the source and know channel_names
        # (eg before a dastard source is started) we will need to rebuild it later
        self.mapContainer.layout().addWidget(self.crm_map)

    def deleteCRMMap(self):
        if self.crm_map is not None:
            self.crm_map.parent = None
            self.crm_map.deleteLater()
            self.crm_map = None

    def handleStatusUpdate(self, is_running, source_name, ngroup, nrow):
        if not is_running:
            return self.handleStop()
        # A hack for now to not count error channels.
        self.cols = ngroup
        self.rows = nrow
        self.deleteCRMGrid()
        self.deleteCRMMap()

    def handleStop(self):
        self.cols = 0
        self.rows = 0
        self.deleteCRMGrid()
        self.deleteCRMMap()

    @pyqtSlot()
    def resetIntegration(self):
        self.countsSeens = []
        if self.crm_grid is not None:
            self.crm_grid.setCountRates(np.zeros(len(self.crm_grid.buttons)), 1)
        self.setArrayCps(0, False, 0)

    def handleAutoScaleClicked(self):
        self.doubleSpinBox_colorScale.setEnabled(not self.pushButton_autoScale.isChecked())
        self.lastTotalRate = 0  # make sure auto scale actually happens

    def handleLoadMap(self):
        if self.host == "localhost":
            file, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select a TES map file", self.mapfile,
                "Maps (*.cfg *.txt)")
            if file == "":
                return
        else:
            file, okay = QtWidgets.QInputDialog.getText(
                self, "Choose map file",
                "Enter full path to map file on %s (remote server):" % self.host,
                QtWidgets.QLineEdit.Normal, self.mapfile)
            if not okay or file == "":
                return
        okay = self.client.call("MapServer.Load", file)

    def handleTESMapFile(self, filename):
        self.mapfile = filename
        head, tail = os.path.split(filename)
        self.mapFileLabel.setText("Map File: %s" % tail)

    def handleTESMap(self, msg):
        scale = 1.0/float(msg["Spacing"])
        minx = np.min([p["X"] for p in msg["Pixels"]])
        maxy = np.max([p["Y"] for p in msg["Pixels"]])
        print("MinX = ", minx, " MaxY=", maxy)
        self.pixelMap = [((p["X"]-minx)*scale, (maxy-p["Y"])*scale) for p in msg["Pixels"]]
        print("handleTESMap with spacing ", msg["Spacing"], " scale ", scale)
        # print(self.pixelMap)
        self.buildCRMMap()

    def handleExternalTriggerMessage(self, msg):
        n = msg["NumberObservedInLastSecond"]
        self.label_externalTriggersInLastSecond.setText(
            "{} external triggers in last second".format(n))

    def handleWritingMessage(self, msg):
        if msg["Active"]:
            print("Observe got Writing Active=True message, resetting state labels")
            self.ExperimentStateIncrementer.resetStateLabels()


class CountRateMap(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""
    buttonFont = QtGui.QFont("Times", 7, QtGui.QFont.Bold)

    def __init__(self, parent, cols, rows, channel_names, xy=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.buttons = []
        self.cols = cols
        self.rows = rows
        self.channel_names = channel_names
        if xy is None:
            self.initButtons(scale=25)
        else:
            self.initButtons(scale=23, xy=xy)

    def addButton(self, x, y, xwidth, ywidth, tooltip):
        button = QtWidgets.QPushButton(self)
        button.move(x, y)
        button.setFixedSize(xwidth, ywidth)
        button.setFont(self.buttonFont)
        button.setFlat(False)
        button.setToolTip(tooltip)
        # button.setCheckable(True)
        self.buttons.append(button)

    def deleteButtons(self):
        for button in self.buttons:
            if button is None:
                continue
            button.setParent(None)
            button.deleteLater()
        self.buttons = []

    def setColsRows(self, cols, rows):
        if cols != self.cols or rows != self.rows:
            self.cols = cols
            self.rows = rows
            self.initButtons()

    def initButtons(self, scale=25, xy=None):
        self.deleteButtons()
        print(self.channel_names)
        row = col = i = 0
        for name in self.channel_names:
            if not name.startswith("chan"):
                self.buttons.append(None)
                continue
            if xy is None:
                x = scale*row
                y = scale*col
            else:
                x = scale*xy[i][0]
                y = scale*xy[i][1]
            self.addButton(x, y, scale-1, scale-1,
                           "{}, row{}col{} matterchan{}".format(name, row, col, 2*(self.rows*col+row)+1))
            row += 1
            i += 1
            if row >= self.rows:
                row = 0
                col += 1

    def setCountRates(self, countRates, colorScale):
        colorScale = float(colorScale)
        assert(len(countRates) == len(self.buttons))
        # cmap = cm.get_cmap('YlOrRd')
        cmap = cm.get_cmap('Wistia')
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

            color = cmap(cr/colorScale, bytes=True)
            colorString = "rgb({},{},{})".format(color[0], color[1], color[2])
            colorString = 'QPushButton {background-color: %s;}' % colorString
            button.setStyleSheet(colorString)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    obs = Observe()
    obs.setColsRows(4, 4)
    obs.setColsRows(10, 10)
    obs.setColsRows(8, 32)
    obs.crm.setCountRates(np.arange(obs.crm.cols*obs.crm.rows), obs.crm.cols*obs.crm.rows)
    # obs.crm.deleteButtons()
    # obs.crm.initButtons()

    obs.show()
    sys.exit(app.exec_())
