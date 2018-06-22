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
        self.writing = False
        self.ui.writingStartButton.setChecked(False)
        self.ui.writingCommentsButton.setEnabled(False)
        self.ui.writingPauseButton.setEnabled(False)

        # Signals/slots
        self.ui.writingStartButton.pressed.connect(self.startstop)
        self.ui.writingCommentsButton.pressed.connect(self.comment)
        self.ui.writingPauseButton.clicked.connect(self.pause)
        cbd = self.ui.changeBaseDirectoryButton
        if host == "localhost" or host == "127.0.0.1":
            cbd.pressed.connect(self.pathSelect)
            cbd.setToolTip("Launch dialog to choose data writing path")
        else:
            cbd.setEnabled(False)
            cbd.setToolTip("Dialog to choose data writing path disabled for remote clients.")

    def handleWritingMessage(self, message):
        if message["Active"]:
            self.startedWriting(message["Filename"])
        else:
            self.stoppedWriting()
        self.updatePath(message["BasePath"])
        self.ui.writingPauseButton.setChecked(message["Paused"])

    def updatePath(self, path):
        if len(path) > 0:
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

    def startstop(self):
        if self.writing:
            request = {"Request": "Stop"}
        else:
            request = {
                "Request": "Start",
                "Rec2Write": 0,  # TODO: let user control this value
                "FileType": "LJH2.2",
                "Path": self.ui.baseDirectoryEdit.text()
            }

        try:
            self.client.call("SourceControl.WriteControl", request)
        except Exception as e:
            print "Could not %s writing: "%request["Request"], e

    def stoppedWriting(self):
        self.writing = False
        self.ui.writingStartButton.setText("Start Writing")
        self.ui.fileNameExampleEdit.setText("")
        self.ui.writingCommentsButton.setEnabled(False)
        self.ui.writingPauseButton.setEnabled(False)

    def startedWriting(self, example):
        self.writing = True
        self.ui.writingStartButton.setText("Stop Writing")
        self.ui.fileNameExampleEdit.setText(example)
        self.ui.writingCommentsButton.setEnabled(True)
        self.ui.writingPauseButton.setEnabled(True)

    def pause(self, paused):
        request = "Pause"
        if not paused:
            request = "Unpause"
        self.client.call("SourceControl.WriteControl", {"Request": request})

    def comment(self):
        parent = None
        title = "Enter a comment to be stored"
        label = "Enter a comment to be stored with the data file as comment.txt"
        default = "Operator, settings, purpose..."
        comment, okay = QtWidgets.QInputDialog.getMultiLineText(parent, title, label, default)
        if okay:
            self.client.call("SourceControl.WriteComment", comment)
