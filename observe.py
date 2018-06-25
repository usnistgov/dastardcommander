# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt

import numpy as np
import json

class ObserveTab(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.table = QtWidgets.QTableWidget()
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)
        self.layout.addWidget(self.table)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        self.table.setSizePolicy(sizePolicy)

        self.label = QtWidgets.QLabel("????",parent=self)
        self.layout.addWidget(self.label)
        self.cols = 1
        self.rows = 1
        self.initTable()

    def handleTriggerRateMessage(self, d):
        if self.cols != self.table.columnCount() or self.rows != self.table.rowCount():
            self.initTable()

        for i,c in enumerate(d["CountsSeen"]):
            row = i
            col = 0
            item = self.table.item(row,col)
            item.setText(str(c))
            self.table.setItem(row,col, item)
            print("row {}, col {}, item {}".format(row,col,item))

        self.label.setText("{} cps".format(np.sum(d["CountsSeen"])))

    def handleStatusUpdate(self, d):
        cols = d.get("Ncol", [])
        rows = d.get("Nrow", [])
        self.nchannels = d["Nchannels"]
        if cols == []:
            self.cols = 1
            self.rows = self.nchannels
        else:
            self.cols = cols
            self.rows = rows

    def initTable(self):
        self.table.setColumnCount(self.cols)
        self.table.setRowCount(self.rows)
        for r in range(self.rows):
            for c in range(self.cols):
                item = QtWidgets.QTableWidgetItem("0")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r,c,item)
        self.table.setColumnWidth()
