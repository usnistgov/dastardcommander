#!/usr/bin/env python

import sys
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets

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
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.reconnect = False
        self.ui.disconnectButton.clicked.connect(self.closeReconnect)

    def printHost(self):
        print "%s:%d"%(self.ui.hostName.text(), self.ui.basePortSpin.value())

    def closeReconnect(self):
        self.reconnect = True
        self.close()


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
        print "Dastard is at %s:%d"%(host,port)

        myapp = MainWindow()
        myapp.show()

        retval = app.exec_()
        if not myapp.reconnect:
            sys.exit(retval)


if __name__ == "__main__": main()
