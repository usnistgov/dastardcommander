# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt

Ui_Writing, _ = PyQt5.uic.loadUiType("writing.ui")


class WritingControl(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""

    def __init__(self, parent=None, host=""):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_Writing()
        self.ui.setupUi(self)
        self.host = host

        # Signals/slots
        cbd = self.ui.changeBaseDirectoryButton
        if host == "localhost" or host == "127.0.0.1":
            cbd.pressed.connect(self.pathSelect)
            cbd.setToolTip("Launch dialog to choose data writing path")
        else:
            cbd.setEnabled(False)
            cbd.setToolTip("Dialog to choose data writing path disabled for remote clients.")


    def updatePath(self, path):
        self.ui.baseDirectoryEdit.setText(path)

    def pathSelect(self):
        """The GUI to select a path"""
        startPath = self.ui.baseDirectoryEdit.text()
        if len(startPath) == 0:
            startPath = "/"
        result = QtWidgets.QFileDialog.getExistingDirectory(None, "Choose base path",
            startPath)
        print "Result was: ", result
        if len(result) > 0:
            self.updatePath(result)
