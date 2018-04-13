import sys
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets

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
        self.ui.hostName.textChanged.connect(self.printHost)
        self.ui.basePortSpin.valueChanged.connect(self.printHost)

    def printHost(self):
        print "%s:%d"%(self.ui.hostName.text(), self.ui.basePortSpin.value())


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    myapp = MainWindow()
    myapp.show()
    sys.exit(app.exec_())
    
