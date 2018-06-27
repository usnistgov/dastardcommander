# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt

import numpy as np
import json
from matplotlib import cm

Ui_Observe, _ = PyQt5.uic.loadUiType("observe.ui")

class Observe(QtWidgets.QWidget):
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_Observe()
        self.ui.setupUi(self)
        self.ui.pushButton_resetIntegration.clicked.connect(self.resetIntegration)
        self.ui.pushButton_autoScale.clicked.connect(self.handleAutoScaleClicked)
        self.crm = None
        self.countsSeens = []
        self.seenStatus = False
        self.lastTotalRate = 0
        self.channel_names = None

    def handleTriggerRateMessage(self, d):
        if self.seenStatus:
            countsSeen = np.array(d["CountsSeen"])
            integrationTime = self.ui.spinBox_integrationTime.value()
            self.countsSeens.append(countsSeen)
            n = min(len(self.countsSeens),integrationTime)
            self.countsSeens = self.countsSeens[-n:]
            countRates = np.zeros(len(countsSeen))
            for cs in self.countsSeens:
                countRates += cs
            countRates /= len(self.countsSeens)
            colorScale = self.getColorScale(countRates)
            self.crm.setCountRates(countRates, colorScale)
            integrationComplete = len(self.countsSeens)==integrationTime
            arrayCps = countRates.sum()
            self.setArrayCps(arrayCps, integrationComplete)
        else:
            print("got trigger rate message before status")

    def getColorScale(self, countRates):
        if self.ui.pushButton_autoScale.isChecked():
            totalRate = countRates.sum()
            fracDiff = np.abs(self.lastTotalRate-totalRate)/(self.lastTotalRate+totalRate)
            self.lastTotalRate=totalRate
            if fracDiff > 0.2:
                print ("autoScale!!")
                maxRate = np.amax(countRates)
                self.ui.doubleSpinBox_colorScale.setValue(maxRate)
        return self.ui.doubleSpinBox_colorScale.value()



    def setArrayCps(self, arrayCps, integrationComplete):
        s = "{} cps/array".format(arrayCps)
        self.ui.label_arrayCps.setText(s)
        self.ui.label_arrayCps.setEnabled(integrationComplete)


    def getChannelNames(self, cols, rows):
        channel_names = self.channel_names
        if channel_names is None or len(channel_names)<cols*rows:
            channel_names = []
            for row in range(rows):
                for col in range(cols):
                    channel_names.append("r{}c{}".format(row,col))
        assert(len(channel_names)==cols*rows)
        return channel_names

    def setColsRows(self, cols, rows):
        if self.crm is not None:
            self.crm.parent = None
            self.crm.deleteLater()
        self.crm = CountRateMap(self,cols,rows,self.getChannelNames(cols,rows))
        self.ui.verticalLayout_countRateMap.addWidget(self.crm)


    def handleStatusUpdate(self, d):
        cols = d.get("Ncol", [])
        rows = d.get("Nrow", [])
        nchannels = d["Nchannels"]
        if cols == []:
            cols = 1
        if rows == []:
            rows = nchannels
        if rows*cols != nchannels:
            cols = int(ceil(nchannels/float(rows)))
        self.seenStatus = True
        self.setColsRows(cols,rows)

    def resetIntegration(self):
        self.countsSeens = []
        self.crm.setCountRates(np.zeros(len(self.crm.buttons)),1)
        self.setArrayCps(0,False)

    def handleAutoScaleClicked(self):
        self.ui.doubleSpinBox_colorScale.setEnabled(not self.ui.pushButton_autoScale.isChecked())
        self.lastTotalRate = 0 # make sure auto scale actually happens

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


    def addButton(self,x,y,xwidth,ywidth,tooltip):
        button = QtWidgets.QPushButton(self)
        button.move(x,y)
        button.setFixedSize(xwidth,ywidth)
        button.setFont(self.buttonFont)
        button.setFlat(False)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        self.buttons.append(button)

    def deleteButtons(self):
        for button in self.buttons:
            button.setParent(None)
            button.deleteLater()
        self.buttons=[]

    def setColsRows(self,cols,rows):
        if cols != self.cols or rows != self.rows:
            self.cols = cols
            self.rows = rows
            self.initButtons()

    def initButtons(self, scale=25):
        self.deleteButtons()
        print("init rows{} cols{}".format(self.rows,self.cols))
        print(self.channel_names)
        for row in range(self.rows):
            for col in range(self.cols):
                i = row + col*self.rows
                print(i, self.channel_names[i])
                self.addButton(scale*row,scale*col,scale,scale,self.channel_names[i])

    def setCountRates(self, countRates, colorScale):
        colorScale = float(colorScale)
        assert(len(countRates)==len(self.buttons))
        cmap = cm.get_cmap('YlOrRd')
        for i,cr in enumerate(countRates):
            button = self.buttons[i]
            if cr < 10:
                buttonText = "{:.2f}".format(cr)
            elif cr < 100:
                buttonText = "{:.1f}".format(cr)
            else:
                buttonText = "{:.0f}".format(cr)
            button.setText(buttonText)

            color = cmap(cr/colorScale,bytes=True)
            colorString = "rgb({},{},{})".format(color[0],color[1],color[2])
            colorString = 'QPushButton {background-color: %s;}'%colorString
            button.setStyleSheet(colorString)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    obs = Observe()
    obs.setColsRows(4,4)
    obs.setColsRows(10,10)
    obs.setColsRows(8,32)
    obs.crm.setCountRates(np.arange(obs.crm.cols*obs.crm.rows),obs.crm.cols*obs.crm.rows)
    # obs.crm.deleteButtons()
    # obs.crm.initButtons()

    obs.show()
    sys.exit(app.exec_())
