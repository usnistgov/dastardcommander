# Qt5 imports
import PyQt5.uic
from PyQt5.QtCore import pyqtSlot
from PyQt5 import QtWidgets

# other non  user imports
import numpy as np
import os


class WritingControl(QtWidgets.QWidget):
    """Provide the UI inside the Triggering tab.

    Most of the UI is copied from MATTER, but the Python implementation in this
    class is new."""

    maraschino = "#ff2600"
    moss = "#008f00"

    def __init__(self, parent, host, client):
        QtWidgets.QWidget.__init__(self, parent)
        self.client = client
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/writing.ui"), self)
        self.host = host
        self.writing = False
        self.writingStartButton.setChecked(False)
        self.writingCommentsButton.setEnabled(False)
        self.writingPauseButton.setEnabled(False)

        # Signals/slots
        self.writingStartButton.pressed.connect(self.startstop)
        self.writingCommentsButton.pressed.connect(self.comment)
        self.writingPauseButton.clicked.connect(self.pause)
        self.checkBox_LJH22.clicked.connect(self.updateWritingActiveMessages)
        self.checkBox_OFF.clicked.connect(self.updateWritingActiveMessages)

        cbd = self.changeBaseDirectoryButton
        if host == "localhost" or host == "127.0.0.1":
            cbd.pressed.connect(self.pathSelect)
            cbd.setToolTip("Launch dialog to choose data writing path")
        else:
            cbd.setEnabled(False)
            cbd.setToolTip("Dialog to choose data writing path disabled for remote clients.")

    def handleWritingMessage(self, message):
        print(message)
        if message["Active"]:
            if len(message["FilenamePattern"]) > 0:
                # FilenamePattern is a format strings such as /a/b/c/c_run0000_%s.%s
                exampleFilename = message["FilenamePattern"] % ("chan*", "ljh")
            else:
                exampleFilename = ""
            self.startedWriting(exampleFilename)
        else:
            self.stoppedWriting()
        self.updatePath(message["BasePath"])
        self.writingPauseButton.setChecked(message["Paused"])

    def updatePath(self, path):
        if len(path) > 0:
            self.baseDirectoryEdit.setText(path)

    def pathSelect(self):
        """The GUI to select a path"""
        startPath = self.baseDirectoryEdit.text()
        if len(startPath) == 0:
            startPath = "/"
        result = QtWidgets.QFileDialog.getExistingDirectory(
            None, "Choose base path", startPath)
        print("Result was: ", result)
        if len(result) > 0:
            self.updatePath(result)

    def handleNumberWritten(self, d):
        Nwritten = np.sum(d["NumberWritten"])
        written_message = f"{Nwritten}"
        if self.stopAtNRecords.isEnabled():
            Nmax = self.stopAtNRecords.value()
            pct = Nwritten * 100.0 / Nmax
            written_message += f" ({pct:.2f}% of the automatic shutoff value)"
            if Nmax > 0 and Nwritten >= Nmax and self.writing:
                self.stop()
        self.label_numberWritten.setText("Number Written Total: {}\nNumber Written by Channel: {}".format(
            written_message, d["NumberWritten"]))

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
                "Path": self.baseDirectoryEdit.text(),
                "WriteLJH22": self.checkBox_LJH22.isChecked(),
                "WriteLJH3": self.checkBox_LJH3.isChecked(),
                "WriteOFF": self.checkBox_OFF.isChecked()
            }

        self.client.call("SourceControl.WriteControl", request)

    def stoppedWriting(self):
        print("STOPPED WRITING")
        self.writing = False
        self.writingStartButton.setText("Start Writing")
        self.previousNameExampleEdit.setText(self.fileNameExampleEdit.text())
        self.fileNameExampleEdit.setText("-")
        self.writingCommentsButton.setEnabled(False)
        self.writingPauseButton.setEnabled(False)
        self.updateWritingActiveMessages()

    def startedWriting(self, exampleFilename):
        print("STARTED WRITING")
        self.writing = True
        self.writingStartButton.setText("Stop Writing")
        self.fileNameExampleEdit.setText(exampleFilename)
        self.writingCommentsButton.setEnabled(True)
        self.writingPauseButton.setEnabled(True)
        self.updateWritingActiveMessages()

    @pyqtSlot()
    def updateWritingActiveMessages(self):
        labels = (self.label_LJH22, self.label_OFF)
        checks = (self.checkBox_LJH22, self.checkBox_OFF)
        for (label, check) in zip(labels, checks):
            if self.writing and check.isChecked():
                label.setText("Writing active")
                color = self.moss
            else:
                label.setText("Not writing")
                color = self.maraschino
            ss = f"QLabel {{ color : {color}; }}"
            label.setStyleSheet(ss)

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
        dialog.textValueSelected.connect(lambda x: self.client.call(
            "SourceControl.WriteComment", dialog.textValue()))
        dialog.show()
