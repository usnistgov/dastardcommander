#!/usr/bin/env python

import sys
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
# from PyQt5.QtWidgets import (QMainWindow, QDialog, QApplication,
#                              QLineEdit, QPushButton, QFormLayout, QMessageBox, QWidget)

import socket
import rpc_client

# Here is how you try to import compiled UI files and fall back to processing them
# at load time via PyQt5.uic. But for now, with frequent changes, let's process all
# at load time.
# try:
#     from dc_ui import Ui_MainWindow
# except ImportError:
#     Ui_MainWindow, _ = PyQt5.uic.loadUiType("dc.ui")
#
# TODO: don't process ui files at run-time, but compile them.

Ui_MainWindow, _ = PyQt5.uic.loadUiType("dc.ui")
Ui_Dialog, _ = PyQt5.uic.loadUiType("host_port.ui")



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, rpc_client, parent=None):
        self.client = rpc_client

        QtWidgets.QMainWindow.__init__(self, parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.reconnect = False
        self.ui.disconnectButton.clicked.connect(self.closeReconnect)
        self.ui.actionDisconnect.triggered.connect(self.closeReconnect)
        self.ui.startStopButton.clicked.connect(self.startStop)
        self.ui.dataSourcesStackedWidget.setCurrentIndex(self.ui.dataSource.currentIndex())
        self.running = False
        self.lanceroCheckBoxes = {}
        self.updateLanceroCardChoices()
        self.buildLanceroFiberBoxes(8)

    def updateLanceroCardChoices(self):
        """Build the check boxes to specify which Lancero cards to use."""

        lo = self.ui.lanceroChooserLayout
        # Empty the layout
        while True:
            item = lo.takeAt(0)
            if item is None:
                break
            if item is not self.ui.noLanceroLabel:
                del item

        cards = [] # TODO: Query the server for the cards it found.
        self.lanceroCheckBoxes = {}
        if len(cards) == 0:
            lo.addWidget(self.ui.noLanceroLabel)
        for c in cards:
            cb = QtWidgets.QCheckBox("lancero %d"%c)
            self.lanceroCheckBoxes[c] = cb
            lo.addWidget(cb)


    def buildLanceroFiberBoxes(self, nfibers):
        """Build the check boxes to specify which fibers to use."""
        lo = self.ui.lanceroFiberLayout
        self.fiberBoxes = {}
        for i in range(nfibers):
            box = QtWidgets.QCheckBox("%d"%(i+nfibers))
            lo.addWidget(box, i, 1)
            self.fiberBoxes[i+nfibers] = box

            box = QtWidgets.QCheckBox("%d"%i)
            lo.addWidget(box, i, 0)
            self.fiberBoxes[i] = box


        def setAll(value):
            for box in self.fiberBoxes.values():
                box.setChecked(value)
        checkAll = lambda : setAll(True)
        clearAll = lambda : setAll(False)
        self.ui.allFibersButton.clicked.connect(checkAll)
        self.ui.noFibersButton.clicked.connect(clearAll)
        self.toggleParallelStreaming(self.ui.parallelStreaming.isChecked())
        self.ui.parallelStreaming.toggled.connect(self.toggleParallelStreaming)

    def toggleParallelStreaming(self, ps):
        """Make the parallel streaming connection between boxes."""

        nfibers = len(self.fiberBoxes)
        if ps:
            for i in range(nfibers//2):
                box1 = self.fiberBoxes[i]
                box2 = self.fiberBoxes[i+nfibers//2]
                either = box1.isChecked() or box2.isChecked()
                box1.setChecked(either)
                box2.setChecked(either)
                box1.toggled.connect(box2.setChecked)
                box2.toggled.connect(box1.setChecked)
        else:
            for i in range(nfibers//2):
                box1 = self.fiberBoxes[i]
                box2 = self.fiberBoxes[i+nfibers//2]
                box1.toggled.disconnect()
                box2.toggled.disconnect()

    def closeReconnect(self):
        """Close the main window, but don't quit. Instead, ask for a new Dastard connection."""
        self.reconnect = True
        self.close()

    def close(self):
        """Close the main window and also the client connection to a Dastard process."""
        if self.client is not None:
            self.client.close()
        self.client = None
        QtWidgets.QMainWindow.close(self)

    def startStop(self):
        """Slot to handle pressing the Start/Stop data button."""
        if self.running:
            okay = self.client.call("SourceControl.Stop", "")
            if not okay:
                print "Could not Stop data"
                return
            print "Stopping Data"
            self.running = False
            self.ui.startStopButton.setText("Start Data")
            self.ui.dataSource.setEnabled(True)
            self.ui.dataSourcesStackedWidget.setEnabled(True)
            return

        sourceID = self.ui.dataSource.currentIndex()
        if sourceID == 0:
            config = {
                "Nchan": self.ui.triangleNchan.value(),
                "SampleRate": self.ui.triangleSampleRate.value(),
                "Max": self.ui.triangleMaximum.value(),
                "Min": self.ui.triangleMinimum.value(),
            }
            okay = self.client.call("SourceControl.ConfigureTriangleSource", config)
            if not okay:
                print "Could not ConfigureTriangleSource"
                return
            okay = self.client.call("SourceControl.Start", "TRIANGLESOURCE")
            if not okay:
                print "Could not Start Triangle "
                return
            print "Starting Triangle"

        elif sourceID == 1:
            config = {
                "Nchan": self.ui.simPulseNchan.value(),
                "SampleRate": self.ui.simPulseSampleRate.value(),
                "Amplitude": self.ui.simPulseAmplitude.value(),
                "Pedestal": self.ui.simPulseBaseline.value(),
                "Nsamp": self.ui.simPulseSamplesPerPulse.value(),
            }
            okay = self.client.call("SourceControl.ConfigureSimPulseSource", config)
            if not okay:
                print "Could not ConfigureSimPulseSource"
                return
            okay = self.client.call("SourceControl.Start", "SIMPULSESOURCE")
            if not okay:
                print "Could not Start SimPulse"
                return
            print "Starting Sim Pulses"

        else:
            return

        self.running = True
        self.ui.startStopButton.setText("Stop Data")
        self.ui.dataSource.setEnabled(False)
        self.ui.dataSourcesStackedWidget.setEnabled(False)
        print self.client.call("SourceControl.Multiply", {"A":13, "B":4})


class HostPortDialog(QtWidgets.QInputDialog):
    def __init__(self, host, port, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.ui.hostName.setText(host)
        self.ui.basePortSpin.setValue(port)

    def run(self):
        retval = self.exec_()
        if retval != QtWidgets.QDialog.Accepted:
            return (None, None)

        host = self.ui.hostName.text()
        port = self.ui.basePortSpin.value()
        return (host, port)


def main():
    app = QtWidgets.QApplication(sys.argv)
    host,port = "localhost",5500

    while True:
        # Ask user what host:port to connect to.
        # TODO: accept a command-line argument to specify host:port. If given,
        # then we'll bypass this dialog the first time through the loop.
        d = HostPortDialog(host=host, port=port)
        host, port = d.run()
        if host is None or port is None:
            print "Could not start Dastard-commander without a valid host:port selection."
            return
        try:
            client = rpc_client.JSONClient((host, port))
        except socket.error:
            print "Could not connect to Dastard at %s:%d"%(host, port)
            continue
        print "Dastard is at %s:%d"%(host,port)

        myapp = MainWindow(client)
        myapp.show()

        retval = app.exec_()
        if not myapp.reconnect:
            sys.exit(retval)


if __name__ == "__main__": main()
