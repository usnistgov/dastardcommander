# Qt5 imports
import PyQt5.uic
from PyQt5 import QtWidgets
from PyQt5.QtCore import QSettings, pyqtSignal

import numpy as np
import time
import subprocess
import os
import glob
import sys

# usercode imports


class ProjectorCaller:
    "A class that can make projectors."

    def __init__(self):
        pass

    @staticmethod
    def scriptcall(scriptname, args, wait=True):
        cmd = ["nice", "-n", "19"]
        cmd.append(scriptname)
        cmd.extend(args)
        print(cmd)
        print(f"""Running '{" ".join(cmd)}'""")
        # we don't use check_call here because Popen prints output in real time, while check_call does not
        p = subprocess.Popen(cmd)
        if wait:
            returncode = p.wait()
            if returncode != 0:
                raise OSError("return code on '{}': {}".format(" ".join(cmd), returncode))

    def createBasis(self, pulseFile, noiseFile, invertPulses):
        args = ["--n_basis", "5", pulseFile, noiseFile]
        if invertPulses:
            args = args[:2] + ["--invert_data"] + args[2:]
        self.scriptcall("make_projectors", args)

    @staticmethod
    def plotBasis(outName):
        raise Exception("not yet implemented")


class Workflow(QtWidgets.QWidget):
    """The tricky bit about this widget is that it cannot be properly set up until
    dc has processed both a CHANNELNAMES message and a STATUS message (to get the
    number of rows and columns)."""

    def __init__(self, dc, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/workflow.ui"), self)
        self.pushButton_takeNoise.clicked.connect(self.handleTakeNoise)
        self.pushButton_takePulses.clicked.connect(self.handleTakePulses)
        self.pushButton_createProjectors.clicked.connect(self.handleCreateProjectors)
        self.pushButton_loadProjectors.clicked.connect(self.handleLoadProjectors)
        self.pushButton_viewProjectorsPlot.clicked.connect(self.handleViewProjectorsPlot)
        self.dc = dc
        self.channel_names = None  # to be overwritten by dc.py
        self.channel_prefixes = None  # to be overwritten by dc.py
        self.nsamples = None  # to be set by handleStatusUpdate
        self.npresamples = None  # to be set by handleStatusUpdate
        self.numberWritten = 0  # to be set by handleNumberWritten
        self.NumberOfChans = None  # to be set by handleNumberWritten
        self.currentlyWriting = None  # to be set by handleWritingMessage
        self.reset()

        self.pcaller = ProjectorCaller()
        self.settings = QSettings()
        self.checkBox_invertPulses.setChecked(bool(self.settings.value("invert_pulses", False)))
        self.checkBox_invertPulses.stateChanged.connect(self.handleCheckBoxStateChanged)
        # self.testingInit() # REMOVE

    # Allow us to connect loading of projectors to the OFF file check box in the writing tab.
    projectorsLoadedSig = pyqtSignal(bool)

    def handleCheckBoxStateChanged(self):
        self.settings.setValue("invert_pulses", self.checkBox_invertPulses.isChecked())

    def testingInit(self):
        """
        pre-populate the output of some steps for faster testing
        to be removed
        """
        self.pulseFilename = "/Users/oneilg/mass/mass/regression_test/regress_chan*.ljh"
        self.noiseFilename = "/Users/oneilg/mass/mass/regression_test/regress_noise_chan*.ljh"
        self.label_noiseFile.setText(f"current noise file: {self.noiseFilename}")
        self.label_pulseFile.setText(f"current pulse file: {self.pulseFilename}")
        self.pushButton_createProjectors.setEnabled(True)

    def reset(self):
        self.noiseFilename = None
        self.label_noiseFile.setText(f"noise data: {self.noiseFilename}")
        self.pulseFilename = None
        self.label_pulseFile.setText(f"pulse data: {self.pulseFilename}")
        self.projectorsFilename = None
        self.pushButton_createProjectors.setEnabled(False)
        self.label_projectors.setText(f"projectors file: {self.projectorsFilename}")
        self.projectorsPlotFilename = None
        self.pushButton_viewProjectorsPlot.setEnabled(False)
        self.pushButton_loadProjectors.setEnabled(False)
        self.label_loadedProjectors.setText("projectors loaded? no")

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
        self.dc.triggerTabSimple.handleSendNoise()
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
                                                TIME_UNITS_TO_WAIT - 1, parent=self)
        progressBar.setModal(True)  # prevent users from clicking elsewhere in gui
        progressBar.show()
        for i in range(TIME_UNITS_TO_WAIT):
            time.sleep(0.1)
            # remember filenames
            self.noiseFilename = self.dc.writingTab.fileNameExampleEdit.text()
            self.label_noiseFile.setText(f"noise data: {self.noiseFilename}")
            progressBar.setLabelText(f"noise, {self.numberWritten} records")
            progressBar.setValue(i)
            QtWidgets.QApplication.processEvents()  # process gui events
            if progressBar.wasCanceled():
                break  # should I do anything else here, like invalidate the data?
        progressBar.close()

        # # stop writing files
        self.dc.writingTab.stop()

    def handleTakePulses(self):
        """
        take pulse data, record filename for future use
        """
        print(self.channel_names)
        if self.currentlyWriting:
            em = QtWidgets.QErrorMessage(self)
            em.showMessage("dastard is currently writing, stop it and try again")
            return
        self.dc.triggerTabSimple.handleSendPulse()
        # start writing files
        self.dc.writingTab.start()
        comment = """Pulse Data for analysis training\nWorkflow: Take Pulses button pushed"""
        self.dc.client.call("SourceControl.WriteComment", comment)
        # wait for 1000 records/channels
        # dont know how to do this yet, so lets just wait for 3 seconds
        # its more important than in the noise case to count written records
        RECORDS_PER_CHANNEL = 1000
        RECORDS_TOTAL = RECORDS_PER_CHANNEL * self.NumberOfChans
        # arguments are label text, cancel button text, minimum value, maximum value
        # None for cancel button text makes there be no cancel button
        progressBar = QtWidgets.QProgressDialog("taking pulses...", "Stop Early",
                                                0, RECORDS_TOTAL, parent=self)
        progressBar.setModal(True)  # prevent users from clicking elsewhere in gui
        progressBar.show()
        self.dc.tabWidget.setCurrentWidget(self.dc.tabObserve)
        self.numberWritten = 0
        while self.numberWritten < RECORDS_TOTAL:
            time.sleep(0.1)
            # remember filenames
            self.pulseFilename = self.dc.writingTab.fileNameExampleEdit.text()
            self.label_pulseFile.setText(f"pulse data: {self.pulseFilename}")
            progressBar.setLabelText(
                f"pulses, {self.numberWritten}/{RECORDS_TOTAL} records")
            progressBar.setValue(self.numberWritten)
            QtWidgets.QApplication.processEvents()  # process gui events
            if progressBar.wasCanceled():
                break  # should I do anything else here, like invalidate the data?
        progressBar.close()
        self.dc.tabWidget.setCurrentWidget(self.dc.tabWorkflow)

        # Stop writing files
        self.dc.writingTab.stop()

        # Enable next step
        self.pushButton_createProjectors.setEnabled(True)

    def openPdf(self, path):
        if not path.endswith(".pdf"):
            raise Exception(f"path should end with .pdf, got {path}")
        print(sys.platform)
        print(self.noisePlotFilename)
        if sys.platform.startswith('darwin'):
            cmd = ["open", path]
        elif sys.platform.startswith('linux'):
            cmd = ["evince", path]
        else:
            raise Exception(f"pdf view not implement for platform = {sys.platform}")
        print(repr(cmd) + "\n")
        subprocess.Popen(cmd)

    def handleCreateProjectors(self):
        # call pope script
        outName = self.pulseFilename[:-9] + "model.hdf5"
        plotName = self.pulseFilename[:-9] + "model_plots.pdf"
        g = glob.glob(self.pulseFilename)
        if len(g) == 0:
            raise Exception(f"could not find any files matching {self.pulseFilename}")
        pulseFile = g[0]
        gn = glob.glob(self.noiseFilename)
        if len(g) == 0:
            raise Exception(f"could not find any files matching {self.noiseFilename}")
        noiseFile = gn[0]
        print(outName, pulseFile, noiseFile)
        if os.path.isfile(outName):
            print(f"{outName} exists, skipping make_projectors")
        else:
            try:
                self.pcaller.createBasis(pulseFile, noiseFile,
                                         self.checkBox_invertPulses.isChecked())
            except OSError as e:
                dialog = QtWidgets.QMessageBox()
                dialog.setText(f"Create Projectors failed: {e}")
                dialog.exec_()
                return

        self.projectorsFilename = outName
        self.label_projectors.setText(f"projectors: {self.projectorsFilename}")

        self.projectorsPlotFilename = plotName
        self.pushButton_viewProjectorsPlot.setEnabled(True)
        self.pushButton_loadProjectors.setEnabled(True)

    def handleViewProjectorsPlot(self):
        self.openPdf(self.projectorsPlotFilename)

    def handleLoadProjectors(self):
        if self.projectorsFilename is None:
            em = QtWidgets.QErrorMessage(self)
            em.showMessage("projectorsFilename is None, have you run the rest of the workflow?")
            return
        if not os.path.isfile(self.projectorsFilename):
            em = QtWidgets.QErrorMessage(self)
            em.showMessage(f"{self.projectorsFilename} does not exist")
            return
        self.dc.triggerTabSimple.lineEdit_projectors.setText(self.projectorsFilename)
        success = self.dc.triggerTabSimple.handleSendProjectors()
        if success:
            self.label_loadedProjectors.setText("projectors loaded? yes")
            self.projectorsLoadedSig.emit(True)

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
