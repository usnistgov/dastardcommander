# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, Qt

import numpy as np

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
        print(message)
        if message["Active"]:
            if len(message["FilenamePattern"])>0:
                # FilenamePattern is a format strings such as /a/b/c/c_run0000_%s.%s
                exampleFilename = message["FilenamePattern"]%("chan*","ljh")
            else:
                exampleFilename = ""
            self.startedWriting(exampleFilename)
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
        result = QtWidgets.QFileDialog.getExistingDirectory(
            None, "Choose base path", startPath)
        print("Result was: ", result)
        if len(result) > 0:
            self.updatePath(result)

    def handleNumberWritten(self, d):
        self.ui.label_numberWritten.setText("Number Written by Channel: {}\nNumber Written Total: {}".format(d["NumberWritten"],
                                            np.sum(d["NumberWritten"])))

    def start(self):
        if self.writing:
            raise Exception("already writing")
        else:
            self.startstop()

    def stop(self):
        if not self.writing:
            raise Exception("already stopped")
        else:
            self.startstop()

    def startstop(self):
        if self.writing:
            request = {"Request": "Stop"}
        else:
            request = {
                "Request": "Start",
                "Path": self.ui.baseDirectoryEdit.text(),
                "WriteLJH22": self.ui.checkBox_LJH22.isChecked(),
                "WriteLJH3": self.ui.checkBox_LJH3.isChecked(),
                "WriteOFF": self.ui.checkBox_OFF.isChecked()
            }

        self.client.call("SourceControl.WriteControl", request)


    def stoppedWriting(self):
        print("STOPPED WRITING")
        self.writing = False
        self.ui.writingStartButton.setText("Start Writing")
        self.ui.previousNameExampleEdit.setText(self.ui.fileNameExampleEdit.text())
        self.ui.fileNameExampleEdit.setText("-")
        self.ui.writingCommentsButton.setEnabled(False)
        self.ui.writingPauseButton.setEnabled(False)

    def startedWriting(self, exampleFilename):
        print("STARTED WRITING")
        self.writing = True
        self.ui.writingStartButton.setText("Stop Writing")
        self.ui.fileNameExampleEdit.setText(exampleFilename)
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
        reply, error = self.client.call("SourceControl.ReadComment", 0, errorBox=False)
        # The synchronous function getMultiLineText is blocking, which causes us to
        # miss heartbeats and crashes dc. Instead, we build a QInputDialog
        # and connect to a signal
        dialog = QtWidgets.QInputDialog(parent)
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setLabelText(label)
        dialog.setWindowTitle(title)
        if error is None and len(reply) > 0:
            dialog.setTextValue(reply)
        else:
            dialog.setTextValue(default)
        dialog.setOption(QtWidgets.QInputDialog.UsePlainTextEditForTextInput)
        dialog.textValueSelected.connect(lambda x: self.client.call("SourceControl.WriteComment", dialog.textValue()))
        dialog.show()
