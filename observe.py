# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt

import numpy as np
import json
from matplotlib import cm

Ui_Observe, _ = PyQt5.uic.loadUiType("observe.ui")


class Observe(QtWidgets.QWidget):
    """The tricky bit about this widget is that it cannot be properly set up until
    dc has processed both a CHANNELNAMES message and a STATUS message (to get the
    number of rows and columns)."""

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_Observe()
        self.ui.setupUi(self)
        self.ui.pushButton_resetIntegration.clicked.connect(self.resetIntegration)
        self.ui.pushButton_autoScale.clicked.connect(self.handleAutoScaleClicked)
        self.crm = None
        self.countsSeens = []
        self.cols = 0
        self.rows = 0
        self.channel_names = []
        self.auxPerChan = 0
        self.lastTotalRate = 0

    def handleTriggerRateMessage(self, d):
        if self.cols == 0 or self.rows == 0:
            print("got trigger rate message before status")
            return
        if len(self.channel_names) == 0:
            print("got trigger rate message before channel names")
            return
        if self.crm is None:
            self.buildCRM()

        countsSeen = np.array(d["CountsSeen"])
        integrationTime = self.ui.spinBox_integrationTime.value()
        self.countsSeens.append(countsSeen)
        n = min(len(self.countsSeens), integrationTime)
        self.countsSeens = self.countsSeens[-n:]
        countRates = np.zeros(len(countsSeen))
        for cs in self.countsSeens:
            countRates += cs
        countRates /= len(self.countsSeens)
        colorScale = self.getColorScale(countRates)
        self.crm.setCountRates(countRates, colorScale)
        integrationComplete = len(self.countsSeens) == integrationTime
        arrayCps = countRates.sum()
        self.setArrayCps(arrayCps, integrationComplete)

    def getColorScale(self, countRates):
        if self.ui.pushButton_autoScale.isChecked():
            totalRate = countRates.sum()
            fracDiff = np.abs(self.lastTotalRate-totalRate)/(self.lastTotalRate+totalRate)
            self.lastTotalRate = totalRate
            if fracDiff > 0.2:
                print ("autoScale!!")
                maxRate = np.amax(countRates)
                self.ui.doubleSpinBox_colorScale.setValue(maxRate)
        return self.ui.doubleSpinBox_colorScale.value()

    def setArrayCps(self, arrayCps, integrationComplete):
        s = "{} cps/array".format(arrayCps)
        self.ui.label_arrayCps.setText(s)
        self.ui.label_arrayCps.setEnabled(integrationComplete)

    def getChannelNames(self):
        channel_names = self.channel_names
        rows = self.rows
        cols = self.cols
        print "Need channel_names. Have: ", channel_names
        if channel_names is None or len(channel_names) < cols*rows:
            channel_names = []
            for col in range(cols):
                for row in range(rows):
                    channel_names.append("XXr{}c{}chan{}".format(row, col, len(channel_names)))
        assert(len(channel_names) == cols*rows*(1+self.auxPerChan))
        return channel_names

    def buildCRM(self):
        self.deleteCRM()
        self.crm = CountRateMap(self, self.cols, self.rows, self.getChannelNames())
        self.ui.GridTab.layout().addWidget(self.crm)

    def deleteCRM(self):
        if self.crm is not None:
            self.crm.parent = None
            self.crm.deleteLater()
            self.crm = None

    def handleStatusUpdate(self, d):
        if not d["Running"]:
            return self.handleStop()

        # A hack for now to not count error channels.
        if d["SourceName"] == "Lancero":
            self.auxPerChan = 1
        cols = d.get("Ncol", [])
        rows = d.get("Nrow", [])
        nchannels = d["Nchannels"] / (self.auxPerChan+1)
        cols = max(1, sum(cols))
        if len(rows) == 0:
            rows = [1]
        else:
            rows = max(rows)
        print "Rows, cols, nchan: ", rows, cols, nchannels
        # If numbers don't add up, trust the column count
        if rows*cols != nchannels:
            rows = nchannels // cols
            if nchannels % cols > 0:
                rows += 1
        if rows != self.rows or cols != self.cols:
            self.cols = cols
            self.rows = rows
            self.deleteCRM()

    def handleStop(self):
        self.cols = 0
        self.rows = 0
        self.deleteCRM()

    def resetIntegration(self):
        self.countsSeens = []
        self.crm.setCountRates(np.zeros(len(self.crm.buttons)), 1)
        self.setArrayCps(0, False)

    def handleAutoScaleClicked(self):
        self.ui.doubleSpinBox_colorScale.setEnabled(not self.ui.pushButton_autoScale.isChecked())
        self.lastTotalRate = 0  # make sure auto scale actually happens


class CountRateMap(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""
    buttonFont = QtGui.QFont("Times", 10, QtGui.QFont.Bold)

    def __init__(self, parent, cols, rows, channel_names):
        QtWidgets.QWidget.__init__(self, parent)
        self.buttons = []
        self.cols = cols
        self.rows = rows
        self.channel_names = channel_names
        self.initButtons()

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

    def initButtons(self, scale=25):
        self.deleteButtons()
        print(self.channel_names)
        row = col = 0
        for i, name in enumerate(self.channel_names):
            if not name.startswith("chan"):
                self.buttons.append(None)
                continue
            self.addButton(scale*row, scale*col, scale, scale, name)
            row += 1
            if row >= self.rows:
                row = 0
                col += 1

    def setCountRates(self, countRates, colorScale):
        colorScale = float(colorScale)
        assert(len(countRates) == len(self.buttons))
        cmap = cm.get_cmap('plasma')
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
