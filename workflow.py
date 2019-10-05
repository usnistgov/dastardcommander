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
import projectors
from collections import OrderedDict

Ui_Workflow, _ = PyQt5.uic.loadUiType("workflow.ui")


class JuliaCaller(object):
    "A class that can call julia to run POPE scripts"

    def __init__(self):
        """Find which version of julia has POPE installed. Assume that the newest
        is the one you want"""

        versiontext = subprocess.check_output(["julia", "-v"],
                                              encoding="UTF-8").split()[2]
        major = int(versiontext.split(".")[0])
        majorminor = ".".join(versiontext.split(".")[:2])
        if major == 0:
            path = os.path.expanduser("~/.julia/v%s/Pope/scripts" % majorminor)
            if not os.path.isdir(path):
                raise OSError("JuliaCaller could not find ~/.julia/v*/Pope/scripts")
        elif major >= 1:
            path = os.path.expanduser("~/.pope")
        else:
            raise Exception("unrecognized Julia version {}".format(versiontext))
        self.POPE_PATH = path
        print("Found julia version %s" % majorminor)
        print("Found Pope scripts in %s" % path)

    def jcall(self, scriptname, args, wait=True):
        cmd = ["nice","-n","19", os.path.join(self.POPE_PATH, scriptname)]
        cmd.extend(args)
        print("Running '%s'" % " ".join(cmd))
        # we don't use check_call here because Popen prints output in real time, while check_call does not
        p = subprocess.Popen(cmd)
        if wait:
            returncode = p.wait()
            if returncode != 0:
                raise OSError("return code on '{}': {}".format(" ".join(cmd), returncode))

    def createNoise(self, pulseFile):
        args = ["--dontcrash", pulseFile]
        self.jcall("noise_analysis.jl", args)

    def plotNoise(self, outName):
        args = [outName]
        self.jcall("noise_plots.jl", args, wait=False)

    def createBasis(self, pulseFile, noiseModel):
        args = ["--n_basis", "4", "--tsvd_method", "noisemass3", pulseFile, noiseModel]
        self.jcall("basis_create.jl", args)

    def plotBasis(self, outName):
        args = [outName]
        self.jcall("basis_plots.jl", args, wait=False)


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
        self.ui.pushButton_viewProjectorsPlot.clicked.connect(self.handleViewProjectorsPlot)
        self.dc = dc
        self.channel_names = None  # to be overwritten by dc.py
        self.channel_prefixes = None  # to be overwritten by dc.py
        self.nsamples = None  # to be set by handleStatusUpdate
        self.npresamples = None  # to be set by handleStatusUpdate
        self.numberWritten = 0  # to be set by handleNumberWritten
        self.NumberOfChans = None  # to be set by handleNumberWritten
        self.currentlyWriting = None  # to be set by handleWritingMessage
        self.reset()

        try:
            self.julia = JuliaCaller()
        except OSError:
            self.julia = None
            self.ui.pushButton_takeNoise.setEnabled(False)
            self.ui.pushButton_takePulses.setEnabled(False)
            self.ui.pushButton_createNoiseModel.setEnabled(False)
            self.ui.pushButton_createProjectors.setEnabled(False)
        # self.testingInit() # REMOVE

    def testingInit(self):
        """
        pre-populate the output of some steps for faster testing
        to be removed
        """
        self.noiseFilename = "/tmp/20180709/0001/20180709_run0001_chan*.ljh"
        self.pulseFilename = "/tmp/20180709/0000/20180709_run0000_chan*.ljh"
        self.ui.label_noiseFile.setText("current noise file: %s" % self.noiseFilename)
        self.ui.label_pulseFile.setText("current noise file: %s" % self.pulseFilename)
        self.ui.pushButton_createNoiseModel.setEnabled(True)
        self.ui.pushButton_createProjectors.setEnabled(True)


    def reset(self):
        self.noiseFilename = None
        self.ui.label_noiseFile.setText("noise data: %s" % self.noiseFilename)
        self.pulseFilename = None
        self.ui.label_pulseFile.setText("pulse data: %s" % self.pulseFilename)
        self.noiseModelFilename = None
        self.ui.pushButton_createNoiseModel.setEnabled(False)
        self.ui.label_noiseModel.setText("noise model: %s" % self.noiseModelFilename)
        self.noisePlotFilename = None
        self.ui.pushButton_viewNoisePlot.setEnabled(False)
        self.projectorsFilename = None
        self.ui.pushButton_createProjectors.setEnabled(False)
        self.ui.label_projectors.setText("projectors file: %s" % self.projectorsFilename)
        self.projectorsPlotFilename = None
        self.ui.pushButton_viewProjectorsPlot.setEnabled(False)
        self.ui.pushButton_loadProjectors.setEnabled(False)
        self.ui.label_loadedProjectors.setText("projectors loaded? no")


    def handleTakeNoise(self):
        """
        take noise data, record filename for future use
        """
        # set triggers to auto for all fb channels
        self.reset()
        print(self.channel_names)
        if self.currentlyWriting:
            em = QtWidgets.QErrorMessage(self)
            em.showMessage("dastard is currently writing, stop it and try again")
            return
        self.dc.triggerTab.goNoiseMode()
        # start writing files
        self.dc.writingTab.start()

        comment = """Noise Data\nWorkflow: Take Noise button pushed"""
        self.dc.client.call("SourceControl.WriteComment", comment)
        # wait for 1000 records/channels
        # dont know how to do this yet, so lets just wait for 3 seconds
        TIME_UNITS_TO_WAIT = 30
        # arguments are label text, cancel button text, minimum value, maximum value
        # None for cancel button text makes there be no cancel button
        progressBar = QtWidgets.QProgressDialog("taking noise...", "Stop Early", 0,
                                                TIME_UNITS_TO_WAIT-1, parent=self)
        progressBar.setModal(True)  # prevent users from clicking elsewhere in gui
        progressBar.show()
        for i in range(TIME_UNITS_TO_WAIT):
            time.sleep(0.1)
            # remember filenames
            self.noiseFilename = self.dc.writingTab.ui.fileNameExampleEdit.text()
            self.ui.label_noiseFile.setText("noise data: %s" % self.noiseFilename)
            progressBar.setLabelText("noise, {} records".format(self.numberWritten))
            progressBar.setValue(i)
            QtWidgets.QApplication.processEvents()  # process gui events
            if progressBar.wasCanceled():
                break  # should I do anything else here, like invalidate the data?
        progressBar.close()

        # # stop writing files
        self.dc.writingTab.stop()

        #enable next step
        self.ui.pushButton_createNoiseModel.setEnabled(True)


    def handleTakePulses(self):
        """
        take noise data, record filename for future use
        """
        # set triggers to auto for all fb channels
        # this is wrong!!! but I need something here to make progress
        # the best option would be to have Joe implement the "trigger states" buttons
        # and activate the pulses trigger state
        print(self.channel_names)
        if self.currentlyWriting:
            em = QtWidgets.QErrorMessage(self)
            em.showMessage("dastard is currently writing, stop it and try again")
            return
        if self.ui.checkBox_useEdgeMultiForTakePulses.isChecked():
            self.dc.sendEdgeMulti()
        else:
            self.dc.triggerTab.goPulseMode()
        # start writing files
        self.dc.writingTab.start()
        comment = """Pulse Data for analysis training\nWorkflow: Take Pulses button pushed"""
        self.dc.client.call("SourceControl.WriteComment", comment)
        # wait for 1000 records/channels
        # dont know how to do this yet, so lets just wait for 3 seconds
        # its more important than in the noise case to count written records
        RECORDS_PER_CHANNEL = 1000
        RECORDS_TOTAL = RECORDS_PER_CHANNEL*self.NumberOfChans
        # arguments are label text, cancel button text, minimum value, maximum value
        # None for cancel button text makes there be no cancel button
        progressBar = QtWidgets.QProgressDialog("taking pulses...", "Stop Early",
                                                0, RECORDS_TOTAL, parent=self)
        progressBar.setModal(True)  # prevent users from clicking elsewhere in gui
        progressBar.show()
        self.dc.ui.tabWidget.setCurrentWidget(self.dc.ui.tabObserve)
        self.numberWritten = 0
        while self.numberWritten < RECORDS_TOTAL:
            time.sleep(0.1)
            # remember filenames
            self.pulseFilename = self.dc.writingTab.ui.fileNameExampleEdit.text()
            self.ui.label_pulseFile.setText("pulse data: %s" % self.pulseFilename)
            progressBar.setLabelText("pulses, {}/{} records".format(self.numberWritten, RECORDS_TOTAL))
            progressBar.setValue(self.numberWritten)
            QtWidgets.QApplication.processEvents()  # process gui events
            if progressBar.wasCanceled():
                break  # should I do anything else here, like invalidate the data?
        progressBar.close()
        self.dc.ui.tabWidget.setCurrentWidget(self.dc.ui.tabWorkflow)


        # # stop writing files
        self.dc.writingTab.stop()

        #enable next step
        self.ui.pushButton_createProjectors.setEnabled(True)


    def handleCreateNoiseModel(self):
        # create output file name (easier than getting it from script output?)
        # output
        # create pope script call
        outName = self.noiseFilename[:-9]+"noise.hdf5"
        plotName = self.noiseFilename[:-9]+"noise.pdf"
        print(outName)

        inputFile = glob.glob(self.noiseFilename)[0]
        if os.path.isfile(outName):
            print("{} already exists, skipping noise_analysis.jl".format(outName))
        else:
            try:
                self.julia.createNoise(inputFile)
            except OSError as e:
                dialog = QtWidgets.QMessageBox()
                dialog.setText("Create Noise failed: {}".format(e))
                dialog.exec_()
                return

        self.noiseModelFilename = outName
        self.ui.label_noiseModel.setText("noise model: %s" % self.noiseModelFilename)

        if os.path.isfile(plotName):
            print("{} already exists, skipping noise_plots.jl".format(plotName))
        else:
            try:
                self.julia.plotNoise(outName)
            except OSError as e:
                dialog = QtWidgets.QMessageBox()
                dialog.setText("Plot Noise failed: {}".format(e))
                dialog.exec_()
                return

        self.noisePlotFilename = plotName
        self.ui.pushButton_viewNoisePlot.setEnabled(True)

    def openPdf(self, path):
        if not path.endswith(".pdf"):
            raise Exception("path should end with .pdf, got {}".format(path))
        print(sys.platform)
        print(self.noisePlotFilename)
        if sys.platform.startswith('darwin'):
            cmd = ["open", path]
        elif sys.platform.startswith('linux'):
            cmd = ["evince", path]
        else:
            raise Exception("pdf view not implement for platform = {}".format(sys.platform))
        print(repr(cmd)+"\n")
        subprocess.Popen(cmd)

    def handleViewNoisePlot(self):
        self.openPdf(self.noisePlotFilename)

    def handleCreateProjectors(self):
        # call pope script
        outName = self.pulseFilename[:-9]+"model.hdf5"
        plotName = self.pulseFilename[:-9]+"model_plots.pdf"
        print(outName)
        pulseFile = glob.glob(self.pulseFilename)[0]
        if os.path.isfile(outName):
            print("{} exists, skipping create_basis.jl".format(outName))
        else:
            try:
                self.julia.createBasis(pulseFile, self.noiseModelFilename)
            except OSError as e:
                dialog = QtWidgets.QMessageBox()
                dialog.setText("Create Projectors failed: {}".format(e))
                dialog.exec_()
                return

        self.projectorsFilename = outName
        self.ui.label_projectors.setText("projectors: %s" % self.projectorsFilename)

        if os.path.isfile(plotName):
            print("{} already exists, skipping basis_plots.jl".format(plotName))
        else:
            try:
                self.julia.plotBasis(outName)
            except OSError as e:
                dialog = QtWidgets.QMessageBox()
                dialog.setText("Plot Basis failed: {}".format(e))
                dialog.exec_()
                return

        self.projectorsPlotFilename = plotName
        self.ui.pushButton_viewProjectorsPlot.setEnabled(True)
        self.ui.pushButton_loadProjectors.setEnabled(True)


    def handleViewProjectorsPlot(self):
        self.openPdf(self.projectorsPlotFilename)

    def handleLoadProjectors(self):
        if self.projectorsFilename is None:
            em = QtWidgets.QErrorMessage(self)
            em.showMessage("projectorsFilename is None, have you run the rest of the workflow?")
            return
        if not os.path.isfile(self.projectorsFilename):
            em = QtWidgets.QErrorMessage(self)
            em.showMessage("{} does not exist".format(self.projectorsFilename))
            return
        print("opening: {}".format(self.projectorsFilename))
        configs = projectors.getConfigs(self.projectorsFilename, self.dc.channel_names)
        print("Sending model for {} chans".format(len(configs)))
        success_chans = []
        failures = OrderedDict()
        for channelIndex, config in list(configs.items()):
            print("sending ProjectorsBasis for {}".format(channelIndex))
            okay, error = self.dc.client.call("SourceControl.ConfigureProjectorsBasis", config, verbose=False, errorBox=False, throwError=False)
            if okay:
                success_chans.append(channelIndex)
            else:
                failures[channelIndex] = error
        result = "success on channelIndicies (not channelName): {}\n".format(sorted(success_chans)) + "failures:\n" + json.dumps(failures, sort_keys=True, indent=4)
        resultBox = QtWidgets.QMessageBox(self)
        resultBox.setText(result)
        resultBox.show()
        self.ui.label_loadedProjectors.setText("projectors loaded? yes")


    def handleStatusUpdate(self, d):
        if self.nsamples != d["Nsamples"] or self.npresamples != d["Npresamp"]:
            if self.nsamples is not None:  # don't reset on startup
                self.reset()
            self.nsamples = d["Nsamples"]
            self.npresamples = d["Npresamp"]
        self.NumberOfChans = d["Nchannels"]

    def handleNumberWritten(self, d):
        self.numberWritten = np.sum(d["NumberWritten"])

    def handleWritingMessage(self, d):
        self.currentlyWriting = d["Active"]


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    bar = QtWidgets.QProgressDialog("taking noise...", None, 0, 30, parent=None)
    # bar.setWindowModality(PyQt5.WindowModal)
    bar.show()

    i = 0
    while not bar.wasCanceled():
        time.sleep(0.1)
        # remember filesnames
        i += 1
        bar.setValue(i)

    sys.exit(app.exec_())
