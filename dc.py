import sys
from PyQt5 import QtCore, QtGui, QtWidgets

from dc_ui import Ui_MainWindow


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
    
