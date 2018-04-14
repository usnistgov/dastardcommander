#!/usr/bin/env python

import sys
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets

import socket
import rpc_client

# Here is how you try to import compiled UI files and fall back to processing them
# at load time via PyQt5.uic. But for now, with frequent changes, let's process all
# at load time.
# try:
#     from dc_ui import Ui_MainWindow
# except ImportError:
#     Ui_MainWindow, _ = PyQt5.uic.loadUiType("dc.ui")

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
        self.running = False

    def closeReconnect(self):
        self.reconnect = True
        self.close()

    def close(self):
        if self.client is not None:
            self.client.close()
        self.client = None
        QtWidgets.QMainWindow.close(self)

    def startStop(self):
        if self.running:
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
                print "Could not Start(Triangle)"
                return
            print "Starting Triangle"

        elif sourceID == 1:
            print "Starting Sim Pulses"
            return
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
        # TODO: accept a command-line argument to bypass this dialog the first time.
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
