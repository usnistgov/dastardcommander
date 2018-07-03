# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt

import numpy as np
import json
from matplotlib import cm

Ui_Workflow, _ = PyQt5.uic.loadUiType("workflow.ui")


class Workflow(QtWidgets.QWidget):
    """The tricky bit about this widget is that it cannot be properly set up until
    dc has processed both a CHANNELNAMES message and a STATUS message (to get the
    number of rows and columns)."""

    def __init__(self, dc, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_Workflow()
        self.ui.setupUi(self)
        self.ui.pushButton_takeNoise.clicked.connect(self.handleTakeNoise)
        self.ui.pushButton_takePulses.clicked.connect(self.handleTakePulses)
        self.ui.pushButton_createNoiseModel.clicked.connect(self.handleCreateNoiseModel)
        self.ui.pushButton_createProjectors.clicked.connect(self.handleCreateProjectors)
        self.ui.pushButton_loadProjectors.clicked.connect(self.handleLoadProjectors)
        self.dc = dc

    def handleTakeNoise(self):
        raise Exception("not implemented")

    def handleTakePulses(self):
        raise Exception("not implemented")

    def handleCreateNoiseModel(self):
        raise Exception("not implemented")

    def handleCreateProjectors(self):
        raise Exception("not implemented")

    def handleLoadProjectors(self):
        raise Exception("not implemented")
