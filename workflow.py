# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer

import numpy as np
import json
import time
import subprocess
import os
import glob
import sys

Ui_Workflow, _ = PyQt5.uic.loadUiType("workflow.ui")

POPE_PATH = os.path.expanduser("~/.julia/v0.6/Pope/Scripts")
NOISE_ANALYSIS_PATH = os.path.join(POPE_PATH,"noise_analysis.jl")
BASIS_CREATE_PATH = os.path.join(POPE_PATH,"basis_create.jl")
NOISE_PLOT_PATH = os.path.join(POPE_PATH,"noise_plots.jl")
BASIS_PLOT_PATH = os.path.join(POPE_PATH,"basis_plots.jl")
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
        self.ui.pushButton_viewNoisePlot.clicked.connect(self.handleViewNoisePlot)
        self.dc = dc
        self.channel_names = None # to be overwritten by dc.py
        self.channel_prefixes = None  # to be overwritten by dc.py
        self.testingInit()

    def testingInit(self):
        """
        pre-populate the output of some steps for faster testing
        """
        self.noiseFilename = "/tmp/20180706/0007/20180706_run0007_chan*.ljh"
        self.pulseFilename = "/tmp/20180706/0008/20180706_run0008_chan*.ljh"
        self.ui.label_noiseFile.setText("current noise file: %s"%self.noiseFilename)
        self.ui.label_pulseFile.setText("current noise file: %s"%self.pulseFilename)

    def reset(self):
        self.noiseFilename = None
        self.ui.label_noiseFile.setText("noise data: %s"%self.noiseFilename)
        self.pulseFilename = None
        self.ui.label_pulseFile.setText("pulse data: %s"%self.pulseFilename)
        self.noiseModelFilename = None
        self.ui.label_noiseModel.setText("noise model: %s"%self.noiseModelFilename)
        self.noisePlotFilename = None
        self.ui.pushButton_viewNoisePlot.setEnabled(False)


    def handleTakeNoise(self):
        """
        take noise data, record filename for future use
        """
        # set triggers to auto for all fb channels
        self.reset()
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
        TIME_UNITS_TO_WAIT = 4
        # arguments are label text, cancel button text, minimum value, maximum value
        # None for cancel button text makes there be no cancel button
        progressBar = QtWidgets.QProgressDialog("taking pulses (not really, just placeholder code)...",None,0,TIME_UNITS_TO_WAIT-1,parent=self)
        progressBar.setModal(True) # prevent users from clicking elsewhere in gui
        progressBar.show()
        for i in range(TIME_UNITS_TO_WAIT):
            time.sleep(0.1)
            # remember filenames
            self.noiseFilename = self.dc.writing.ui.fileNameExampleEdit.text()
            self.ui.label_noiseFile.setText("noise data: %s"%self.noiseFilename)
            progressBar.setValue(i)
            QtWidgets.QApplication.processEvents() # process gui events
        progressBar.close()

        # # stop writing files
        self.dc.writing.stop()

    def handleTakePulses(self):
        """
        take noise data, record filename for future use
        """
        # set triggers to auto for all fb channels
        # this is wrong!!! but I need something here to make progress
        # the best option would be to have Joe implement the "trigger states" buttons
        # and activate the pulses trigger state
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
        # its more important than in the noise case to count written records
        TIME_UNITS_TO_WAIT = 4
        # arguments are label text, cancel button text, minimum value, maximum value
        # None for cancel button text makes there be no cancel button
        progressBar = QtWidgets.QProgressDialog("taking pulses...",None,0,TIME_UNITS_TO_WAIT-1,parent=self)
        progressBar.setModal(True) # prevent users from clicking elsewhere in gui
        progressBar.show()
        for i in range(TIME_UNITS_TO_WAIT):
            time.sleep(0.1)
            # remember filenames
            self.pulseFilename = self.dc.writing.ui.fileNameExampleEdit.text()
            self.ui.label_pulseFile.setText("pulse data: %s"%self.pulseFilename)
            progressBar.setValue(i)
            QtWidgets.QApplication.processEvents() # process gui events
        progressBar.close()

        # # stop writing files
        self.dc.writing.stop()

    def handleCreateNoiseModel(self):
        # create output file name (easier than getting it from script output?)
        # output
        # create pope script call
        outName = self.noiseFilename[:-9]+"noise.hdf5"
        plotName = self.noiseFilename[:-9]+"noise.pdf"
        print outName
        inputFiles = glob.glob(self.noiseFilename)
        cmd = ["julia",NOISE_ANALYSIS_PATH,"-u"] + inputFiles
        # -u instructs noise_analysis to "update" the file by adding new channels, this shouldn't be
        # neccesary but it doesn't seem to work without it
        print(repr(cmd)+"\n")
        if len(inputFiles) == 0:
            print("found no input files for {}".format(self.noiseFilename))
        elif os.path.isfile(outName):
            print("{} already exists, skipping noise_analysis.jl".format(outName))
        else:
            # check_output throws an error if the process fails
            output = subprocess.check_output(cmd)
            print(output)
        self.noiseModelFilename = outName
        self.ui.label_noiseModel.setText("noise model: %s"%self.noiseModelFilename)

        cmdPlot = ["julia",NOISE_PLOT_PATH, plotName]
        print(repr(cmdPlot)+"\n")
        if os.path.isfile(plotName):
            print("{} already exists, skipping noise_plots.jl".format(plotName))
        else:
            cmdOutput = subprocess.check_output(cmdPlot)
            print(cmdOutput)

        self.noisePlotFilename = plotName
        self.ui.pushButton_viewNoisePlot.setEnabled(True)

    def handleViewNoisePlot(self):
        print sys.platform
        print self.noisePlotFilename
        if sys.platform.startswith('darwin'):
            cmd = ["open", self.noisePlotFilename]
        elif sys.platform.startswith('linux'):
            cmd = ["evince", self.noisePlotFilename]
        else:
            raise Exception("pdf view not implement for platform = {}".format(sys.platform))
        print(repr(cmd)+"\n")
        subprocess.Popen(cmd)

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
