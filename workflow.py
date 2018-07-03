# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer

import numpy as np
import json
import time

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
        self.channel_names = None # to be overwritten by dc.py
        self.channel_prefixes = None  # to be overwritten by dc.py

    def handleTakeNoise(self):
        """
        take noise data, record filename for future use
        """
        # set triggers to auto for all fb channels
        print self.channel_names
        state = {}
        state["ChanNumbers"]=[chan for (chan,name) in enumerate(self.channel_names) if name.startswith("chan")]
        state["AutoTrigger"]=True
        state["AutoDelay"]=0
        print state
        self.dc.client.call("SourceControl.ConfigureTriggers", state)
        # start writing files
        self.dc.writing.start()
        # wait for 1000 records/channels
        # dont know how to do this yet, so lets just wait for 3 seconds
        TIME_UNITS_TO_WAIT = 30
        # arguments are label text, cancel button text, minimum value, maximum value
        # None for cancel button text makes there be no cancel button
        progressBar = QtWidgets.QProgressDialog("taking noise...",None,0,TIME_UNITS_TO_WAIT-1,parent=self)
        progressBar.setModal(True) # prevent users from clicking elsewhere in gui
        progressBar.show()
        for i in range(TIME_UNITS_TO_WAIT):
            time.sleep(0.1)
            # remember filenames
            self.noiseFilename = self.dc.writing.ui.fileNameExampleEdit.text()
            self.ui.label_noiseFile.setText("current noise file: %s"%self.noiseFilename)
            progressBar.setValue(i)
            QtWidgets.QApplication.processEvents() # process gui events
        progressBar.close()

        # # stop writing files
        self.dc.writing.stop()

    def handleTakePulses(self):
        # set triggers to pulse triggers for all fb channels
        # start writing files`
        # wait for 3000 records/channels
        # stop writing files
        # remember filename
        raise Exception("not implemented")

    def handleCreateNoiseModel(self):
        # call pope script
        # remember filename
        # button to view plots
        raise Exception("not implemented")

    def handleCreateProjectors(self):
        # call pope script
        # remember filename
        # button to view plots
        raise Exception("not implemented")

    def handleLoadProjectors(self):
        # load projectors
        raise Exception("not implemented")


if __name__ == "__main__":
    import sys


    app = QtWidgets.QApplication(sys.argv)
    bar = QtWidgets.QProgressDialog("taking noise...",None,0,30,parent=None)
    # bar.setWindowModality(PyQt5.WindowModal)
    bar.show()

    i = 0
    while not bar.wasCanceled():
        time.sleep(0.1)
        # remember filesnames
        i+=1
        bar.setValue(i)

    sys.exit(app.exec_())
