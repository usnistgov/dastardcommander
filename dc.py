#!/usr/bin/env python

"""
dastard-commander (dc.py)

A GUI client to operate and monitor the DASTARD server (Data Acquisition
System for Triggering, Analyzing, and Recording Data).

By Joe Fowler and Galen O'Neil
NIST Boulder Laboratories
May 2018 -
"""

# Non-Qt imports
import json
import socket
import subprocess
import sys
import time
import os
from collections import OrderedDict, defaultdict

# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, QSettings, pyqtSlot
from PyQt5.QtWidgets import QFileDialog

# User code imports
import rpc_client
import status_monitor
import trigger_config
import writing
import projectors
import observe
import workflow

_VERSION = "0.1.0"

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
Ui_HostPortDialog, _ = PyQt5.uic.loadUiType("host_port.ui")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, rpc_client, host, port, parent=None):
        self.client = rpc_client
        self.client.setQtParent(self)
        self.host = host
        self.port = port

        QtWidgets.QMainWindow.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon('dc.png'))
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("dastard-commander %s    (connected to %s:%d)" % (_VERSION, host, port))
        self.reconnect = False
        self.disconnectReason = ""
        self.ui.disconnectButton.clicked.connect(lambda: self.closeReconnect("disconnect button"))
        self.ui.actionDisconnect.triggered.connect(lambda: self.closeReconnect("disconnect menu item"))
        self.ui.startStopButton.clicked.connect(self.startStop)
        self.ui.dataSourcesStackedWidget.setCurrentIndex(self.ui.dataSource.currentIndex())
        self.ui.actionLoad_Projectors_Basis.triggered.connect(self.loadProjectorsBasis)
        self.ui.pushButton_sendEdgeMulti.clicked.connect(self.sendEdgeMulti)
        self.ui.pushButton_sendMix.clicked.connect(self.sendMix)
        self.running = False
        self.lanceroCheckBoxes = {}
        self.updateLanceroCardChoices()
        self.buildLanceroFiberBoxes(8)
        self.triggerTab = trigger_config.TriggerConfig(self.ui.tabTriggering)
        self.triggerTab.client = self.client
        self.writingTab = writing.WritingControl(self.ui.tabWriting, host)
        self.writingTab.client = self.client
        self.observeTab = observe.Observe(self.ui.tabObserve)
        self.workflowTab = workflow.Workflow(self, parent=self.ui.tabWorkflow)

        self.microscopes = []
        self.last_messages = defaultdict(str)
        self.channel_names = []
        self.channel_prefixes = set()
        self.triggerTab.channel_names = self.channel_names
        self.observeTab.channel_names = self.channel_names
        self.triggerTab.channel_prefixes = self.channel_prefixes
        self.workflowTab.channel_names = self.channel_names
        self.workflowTab.channel_prefixes = self.channel_prefixes
        self.ui.launchMicroscopeButton.clicked.connect(self.launchMicroscope)
        self.ui.killAllMicroscopesButton.clicked.connect(self.killAllMicroscopes)
        self.ui.tabWidget.setEnabled(False)
        self.buildStatusBar()

        # The ZMQ update monitor. Must run in its own QThread.
        self.nmsg = 0
        self.zmqthread = QtCore.QThread()
        self.zmqlistener = status_monitor.ZMQListener(host, port)
        self.zmqlistener.message.connect(self.updateReceived)

        # We don't want to make this request until the zmqthread is running.
        # So set it up as a slot to receive the thread's started message.
        def request_status():
            self.client.call("SourceControl.SendAllStatus", "dummy")

        self.zmqlistener.moveToThread(self.zmqthread)
        self.zmqthread.started.connect(request_status)
        self.zmqthread.started.connect(self.zmqlistener.loop)
        QtCore.QTimer.singleShot(0, self.zmqthread.start)

        # A timer to monitor for the heartbeat. If this ever times out, it's because
        # too long has elapsed without receiving a heartbeat from Dstard.  Then we
        # have to close the main window.
        self.hbTimer = QtCore.QTimer()
        self.hbTimer.timeout.connect(lambda: self.closeReconnect("missing heartbeat"))
        self.hbTimeout = 5000  # that is, 5000 ms
        self.hbTimer.start(self.hbTimeout)
        self.fullyConfigured = False

    @pyqtSlot(str, str)
    def updateReceived(self, topic, message):

        try:
            d = json.loads(message)
        except Exception as e:
            print "Error processing status message [topic,msg]: %s, %s" % (
                topic, message)
            print "Error is: %s" % e
            return

        quietTopics = set(["TRIGGERRATE", "NUMBERWRITTEN", "ALIVE"])
        if topic not in quietTopics or self.nmsg < 15:
            print("%s %5d: %s" % (topic, self.nmsg, d))

        if topic == "ALIVE":
            self.heartbeat(d)

        elif topic == "TRIGGERRATE":
            self.observeTab.handleTriggerRateMessage(d)

        # All other messages are ignored if they haven't changed
        elif not self.last_messages[topic] == message:
            if topic == "STATUS":
                self.updateStatusBar(d)
                self.observeTab.handleStatusUpdate(d)
                self._setGuiRunning(d["Running"], d["SourceName"])
                self.triggerTab.updateRecordLengthsFromServer(d["Nsamples"], d["Npresamp"])
                self.workflowTab.handleStatusUpdate(d)

                source = d["SourceName"]
                nchan = d["Nchannels"]
                if source == "Triangles":
                    self.ui.dataSource.setCurrentIndex(0)
                    self.ui.triangleNchan.setValue(nchan)
                elif source == "SimPulses":
                    self.ui.dataSource.setCurrentIndex(1)
                    self.ui.simPulseNchan.setValue(nchan)
                elif source == "Lancero":
                    self.ui.dataSource.setCurrentIndex(2)

            elif topic == "TRIGGER":
                self.triggerTab.handleTriggerMessage(d)

            elif topic == "WRITING":
                self.writingTab.handleWritingMessage(d)
                self.workflowTab.handleWritingMessage(d)

            elif topic == "TRIANGLE":
                self.ui.triangleNchan.setValue(d["Nchan"])
                self.ui.triangleSampleRate.setValue(d["SampleRate"])
                self.ui.triangleMinimum.setValue(d["Min"])
                self.ui.triangleMaximum.setValue(d["Max"])

            elif topic == "SIMPULSE":
                self.ui.simPulseNchan.setValue(d["Nchan"])
                self.ui.simPulseSampleRate.setValue(d["SampleRate"])
                self.ui.simPulseBaseline.setValue(d["Pedestal"])
                self.ui.simPulseAmplitude.setValue(d["Amplitude"])
                self.ui.simPulseSamplesPerPulse.setValue(d["Nsamp"])

            elif topic == "LANCERO":
                self.updateLanceroCardChoices(d["AvailableCards"])
                mask = d["FiberMask"]
                for k, v in self.fiberBoxes.items():
                    v.setChecked(mask & (1 << k))
                ns = d["Nsamp"]
                if ns > 0 and ns <= 16:
                    self.ui.nsampSpinBox.setValue(ns)

            elif topic == "CHANNELNAMES":
                self.channel_names[:] = []   # Careful: don't replace the variable
                self.channel_prefixes.clear()
                for name in d:
                    self.channel_names.append(name)
                    prefix = name.rstrip("1234567890")
                    self.channel_prefixes.add(prefix)
                print "New channames: ", self.channel_names
                self.triggerTab.ui.channelChooserBox.setCurrentIndex(2)
                self.triggerTab.channelChooserChanged()

            elif topic == "TRIGCOUPLING":
                self.triggerTab.handleTrigCoupling(d)

            elif topic == "NUMBERWRITTEN":
                self.writingTab.handleNumberWritten(d)
                self.workflowTab.handleNumberWritten(d)

            elif topic == "NEWDASTARD":
                if self.fullyConfigured:
                    self.fullyConfigured = False
                    self.closeReconnect("New Dastard started")

            else:
                print("%s is not a topic we handle yet." % topic)

        self.nmsg += 1
        self.last_messages[topic] = message

        # Enable the window once the following message types have been received
        require = ("TRIANGLE", "SIMPULSE", "LANCERO")
        allseen = True
        for k in require:
            if k not in self.last_messages:
                allseen = False
                break
        if allseen:
            self.fullyConfigured = True
            self.ui.tabWidget.setEnabled(True)

    def buildStatusBar(self):
        self.statusMainLabel = QtWidgets.QLabel("Server not running. ")
        self.statusFreshLabel = QtWidgets.QLabel("")
        sb = self.statusBar()
        sb.addWidget(self.statusMainLabel)
        sb.addWidget(self.statusFreshLabel)

    def updateStatusBar(self, data):
        run = data["Running"]
        if run:
            status = "%s source active, %d channels" % (
                data["SourceName"], data["Nchannels"])
            cols = data.get("Ncol", [])
            rows = data.get("Nrow", [])
            ndev = min(len(cols), len(rows))
            if ndev == 1:
                status += " (%d rows x %d cols)" % (rows[0], cols[0])
            elif ndev > 1:
                status += " ("
                for i in range(ndev):
                    status += "%d x %d" % (rows[i], cols[i])
                    if i < ndev-1:
                        status += ", "
                status += " rows x cols)"

            self.statusMainLabel.setText(status)
        else:
            self.statusMainLabel.setText("Data source stopped")

    def heartbeat(self, hb):
        # Keep window open another 5 seconds
        self.hbTimer.start(self.hbTimeout)

        mb = hb["DataMB"]
        t = float(hb["Time"])

        def color(c, bg=None):
            ss = "QLabel { color : %s; }" % c
            if bg is not None:
                ss = "QLabel { color : %s; background-color : %s }" % (c, bg)
            self.statusFreshLabel.setStyleSheet(ss)

        if mb <= 0:
            # No data is okay...unless server says it's running!
            if self.running:
                self.statusFreshLabel.setText("no fresh data")
                color("white", bg="red")
            else:
                self.statusFreshLabel.setText("")

        elif t <= 0:
            self.statusFreshLabel.setText("%7.3f MB in 0 s??" % mb)
            color("red")
        else:
            rate = mb / t
            self.statusFreshLabel.setText("%7.3f MB/s" % rate)
            color("green")

    @pyqtSlot()
    def closeEvent(self, event):
        """Cleanly close the zmqlistener and block certain signals in the
        trigger config widget."""
        self.triggerTab._closing()
        self.zmqlistener.running = False
        self.zmqthread.quit()
        self.zmqthread.wait()
        event.accept()

    @pyqtSlot()
    def launchMicroscope(self):
        """Launch one instance of microscope.
        TODO: don't hard-wire in the location of the binary!"""
        try:
            args = ("microscope", "tcp://%s:%d" % (self.host, self.port+2))
            sps = subprocess.Popen(args)
            self.microscopes.append(sps)
        except OSError as e:
            print("Could not launch microscope. Is it in your path?")
            print("Error is: ", e)

    @pyqtSlot()
    def killAllMicroscopes(self):
        """Terminate all instances of microscope launched by this program."""
        while True:
            try:
                m = self.microscopes.pop()
                m.terminate()
            except IndexError:
                return

    def updateLanceroCardChoices(self, cards=None):
        """Build the check boxes to specify which Lancero cards to use.
        cards is a list of integers: which cards are available on the sever"""

        layout = self.ui.lanceroChooserLayout
        # Empty the layout
        while True:
            item = layout.takeAt(0)
            if item is None:
                break
            del item

        self.lanceroCheckBoxes = {}
        self.lanceroDelays = {}
        if cards is None:
            cards = []
        if len(cards) == 0:
            self.ui.noLanceroLabel.show()
        else:
            self.ui.noLanceroLabel.hide()
            layout.addWidget(QtWidgets.QLabel("Card number"), 0, 0)
            layout.addWidget(QtWidgets.QLabel("Card delay"), 0, 1)

        narrow = QtWidgets.QSizePolicy()
        narrow.setHorizontalStretch(2)
        wide = QtWidgets.QSizePolicy()
        wide.setHorizontalStretch(10)

        for i, c in enumerate(cards):
            cb = QtWidgets.QCheckBox("lancero %d" % c)
            cb.setChecked(True)
            cb.setSizePolicy(wide)
            self.lanceroCheckBoxes[c] = cb
            layout.addWidget(cb, i+1, 0)
            sb = QtWidgets.QSpinBox()
            sb.setMinimum(0)
            sb.setMaximum(40)
            sb.setValue(1)
            sb.setSizePolicy(narrow)
            sb.setToolTip("Card delay for card %d" % c)
            self.lanceroDelays[c] = sb
            layout.addWidget(sb, i+1, 1)

    def buildLanceroFiberBoxes(self, nfibers):
        """Build the check boxes to specify which fibers to use."""
        layout = self.ui.lanceroFiberLayout
        self.fiberBoxes = {}
        for i in range(nfibers):
            box = QtWidgets.QCheckBox("%d" % (i+nfibers))
            layout.addWidget(box, i, 1)
            self.fiberBoxes[i+nfibers] = box

            box = QtWidgets.QCheckBox("%d" % i)
            layout.addWidget(box, i, 0)
            self.fiberBoxes[i] = box

        def setAll(value):
            for box in self.fiberBoxes.values():
                box.setChecked(value)

        def checkAll():
            setAll(True)

        def clearAll():
            setAll(False)

        self.ui.allFibersButton.clicked.connect(checkAll)
        self.ui.noFibersButton.clicked.connect(clearAll)
        self.toggleParallelStreaming(self.ui.parallelStreaming.isChecked())
        self.ui.parallelStreaming.toggled.connect(self.toggleParallelStreaming)

    @pyqtSlot(bool)
    def toggleParallelStreaming(self, parallelStream):
        """Make the parallel streaming connection between boxes."""
        nfibers = len(self.fiberBoxes)
        npairs = nfibers//2
        if parallelStream:
            for i in range(npairs):
                box1 = self.fiberBoxes[i]
                box2 = self.fiberBoxes[i+npairs]
                either = box1.isChecked() or box2.isChecked()
                box1.setChecked(either)
                box2.setChecked(either)
                box1.toggled.connect(box2.setChecked)
                box2.toggled.connect(box1.setChecked)
        else:
            for i in range(npairs):
                box1 = self.fiberBoxes[i]
                box2 = self.fiberBoxes[i+npairs]
                box1.toggled.disconnect()
                box2.toggled.disconnect()

    @pyqtSlot(str)
    def closeReconnect(self, disconnectReason):
        """Close the main window, but don't quit. Instead, ask for a new Dastard connection.
        Display the disconnection reason."""
        print("disconnecting because: {}".format(disconnectReason))
        self.disconnectReason = disconnectReason
        self.reconnect = True
        self.close()

    def close(self):
        """Close the main window and also the client connection to a Dastard process."""
        self.hbTimer.stop()
        if self.client is not None:
            self.client.close()
        self.client = None
        QtWidgets.QMainWindow.close(self)

    @pyqtSlot()
    def startStop(self):
        """Slot to handle pressing the Start/Stop data button."""
        if self.running:
            self._stop()
            self._setGuiRunning(False)
        else:
            self._start()
            self._setGuiRunning(True)

    def _stop(self):
        okay, error = self.client.call("SourceControl.Stop", "")
        if not okay:
            print "Could not Stop data"
            return
        print "Stopping Data"

    def _setGuiRunning(self, running, sourceName=""):
        self.running = running
        label = "Start Data"
        if running:
            label = "Stop Data"
        self.ui.startStopButton.setText(label)
        self.ui.dataSource.setEnabled(not running)
        self.ui.dataSourcesStackedWidget.setEnabled(not running)
        self.ui.tabTriggering.setEnabled(running)
        if running:
            self.ui.tabWidget.setCurrentWidget(self.ui.tabTriggering)

        enable = running and (sourceName == "Lancero")
        self.triggerTab.ui.coupleFBToErrCheckBox.setEnabled(enable)
        self.triggerTab.ui.coupleErrToFBCheckBox.setEnabled(enable)
        self.triggerTab.ui.coupleFBToErrCheckBox.setChecked(False)
        self.triggerTab.ui.coupleErrToFBCheckBox.setChecked(False)

    def _start(self):
        sourceID = self.ui.dataSource.currentIndex()
        if sourceID == 0:
            self._startTriangle()
        elif sourceID == 1:
            self._startSimPulse()
        elif sourceID == 2:
            self._startLancero()
        else:
            return

    def _startTriangle(self):
        config = {
            "Nchan": self.ui.triangleNchan.value(),
            "SampleRate": self.ui.triangleSampleRate.value(),
            "Max": self.ui.triangleMaximum.value(),
            "Min": self.ui.triangleMinimum.value(),
        }
        okay, error = self.client.call("SourceControl.ConfigureTriangleSource", config)
        if not okay:
            print "Could not ConfigureTriangleSource"
            return
        okay, error = self.client.call("SourceControl.Start", "TRIANGLESOURCE")
        if not okay:
            print "Could not Start Triangle "
            return
        print "Starting Triangle"

    def _startSimPulse(self):
        config = {
            "Nchan": self.ui.simPulseNchan.value(),
            "SampleRate": self.ui.simPulseSampleRate.value(),
            "Amplitude": self.ui.simPulseAmplitude.value(),
            "Pedestal": self.ui.simPulseBaseline.value(),
            "Nsamp": self.ui.simPulseSamplesPerPulse.value(),
        }
        okay, error = self.client.call("SourceControl.ConfigureSimPulseSource", config)
        if not okay:
            print "Could not ConfigureSimPulseSource"
            return
        okay, error = self.client.call("SourceControl.Start", "SIMPULSESOURCE")
        if not okay:
            print "Could not Start SimPulse"
            return
        print "Starting Sim Pulses"

    def _startLancero(self):
        mask = 0
        for k, v in self.fiberBoxes.items():
            if v.isChecked():
                mask |= (1 << k)
        print("Fiber mask: 0x%4.4x" % mask)
        clock = 125
        if self.ui.lanceroClock50Button.isChecked():
            clock = 50
        nsamp = self.ui.nsampSpinBox.value()

        activate = []
        delays = []
        for k, v in self.lanceroCheckBoxes.items():
            if v.isChecked():
                activate.append(k)
                delays.append(self.lanceroDelays[k].value())

        config = {
            "FiberMask": mask,
            "ClockMhz": clock,
            "CardDelay": delays,
            "Nsamp": nsamp,
            "ActiveCards": activate,
            "AvailableCards": []   # This is filled in only by server, not us.
        }
        print "START LANCERO CONFIG"
        print config
        self.client.call("SourceControl.ConfigureLanceroSource", config, errorBox = True)
        self.client.call("SourceControl.Start", "LANCEROSOURCE", errorBox = True, throwError=False)
        self.triggerTab.ui.coupleFBToErrCheckBox.setEnabled(True)
        self.triggerTab.ui.coupleErrToFBCheckBox.setEnabled(True)
        self.triggerTab.ui.coupleFBToErrCheckBox.setChecked(False)
        self.triggerTab.ui.coupleErrToFBCheckBox.setChecked(False)

    @pyqtSlot()
    def loadProjectorsBasis(self):
        options = QFileDialog.Options()
        if not hasattr(self, "lastdir"):
            dir = os.path.expanduser("~")
        else:
            dir = self.lastdir
        fileName, _ = QFileDialog.getOpenFileName(
            self, "Find Projectors Basis file", dir,
            "Model Files (*_model.hdf5);;All Files (*)", options=options)
        if fileName:
            self.lastdir = os.path.dirname(fileName)
            print("opening: {}".format(fileName))
            configs = projectors.getConfigs(fileName, self.channel_names)
            print("Sending model for {} chans".format(len(configs)))
            success_chans = []
            failures = OrderedDict()
            for channelIndex, config in configs.items():
                print("sending ProjectorsBasis for {}".format(channelIndex))
                okay, error = self.client.call("SourceControl.ConfigureProjectorsBasis", config, verbose=False, errorBox=False, throwError=False)
                if okay:
                    success_chans.append(channelIndex)
                else:
                    failures[channelIndex] = error
            result = "success on channelIndicies (not channelName): {}\n".format(sorted(success_chans)) + "failures:\n" + json.dumps(failures, sort_keys=True, indent=4)
            resultBox = QtWidgets.QMessageBox(self)
            resultBox.setText(result)
            resultBox.show()


    @pyqtSlot()
    def sendEdgeMulti(self):
        config = {
            "ChannelIndicies": range(len(self.channel_names)),
            "EdgeMulti": self.ui.checkBox_EdgeMulti.isChecked(),
            "EdgeRising": self.ui.checkBox_EdgeMulti.isChecked(),
            "EdgeTrigger": self.ui.checkBox_EdgeMulti.isChecked(),
            "EdgeMultiNoise": self.ui.checkBox_EdgeMultiNoise.isChecked(),
            "EdgeMultiMakeShortRecords": self.ui.checkBox_EdgeMultiMakeShortRecords.isChecked(),
            "EdgeMultiMakeContaminatedRecords": self.ui.checkBox_EdgeMultiMakeContaminatedRecords.isChecked(),
            "EdgeMultiVerifyNMonotone": self.ui.spinBox_EdgeMultiVerifyNMonotone.value(),
            "EdgeLevel": self.ui.spinBox_EdgeLevel.value()
        }
        self.client.call("SourceControl.ConfigureTriggers", config)

    @pyqtSlot()
    def sendMix(self):
        mixFraction = self.ui.doubleSpinBox_MixFraction.value()
        if mixFraction == 0.0:
            return

        for i in range(len(self.channel_names)):
            if i % 2 == 0:  # only odd channels get mix
                continue
            config = {
                "ChannelIndex": i,
                "MixFraction": mixFraction
            }
            try:
                self.client.call("SourceControl.ConfigureMixFraction", config)
                print("experimental mix config")
                print config
            except Exception as e:
                print "Could not set mix: {}".format(e)


class HostPortDialog(QtWidgets.QDialog):
    def __init__(self, host, port, disconnectReason, settings, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon('dc.png'))
        self.ui = Ui_HostPortDialog()
        self.ui.setupUi(self)
        self.ui.hostName.setText(host)
        self.ui.basePortSpin.setValue(port)
        self.settings = settings

        if disconnectReason and disconnectReason != "disconnect button":
            # give a clear message about why disconnections happen
            dialog = QtWidgets.QMessageBox()
            dialog.setText("disconnected because: {}".format(disconnectReason))
            dialog.exec_()

    def run(self):
        retval = self.exec_()
        if retval != QtWidgets.QDialog.Accepted:
            return (None, None)

        host = self.ui.hostName.text()
        port = self.ui.basePortSpin.value()
        self.settings.setValue("host", host)
        self.settings.setValue("port", int(port))
        return (host, port)


def main():
    settings = QSettings("NIST Quantum Sensors", "dastard-commander")

    app = QtWidgets.QApplication(sys.argv)
    host = settings.value("host", "localhost", type=str)
    port = settings.value("port", 5500, type=int)
    disconnectReason = ""
    while True:
        # Ask user what host:port to connect to.
        # TODO: accept a command-line argument to specify host:port.
        # If given, we'll bypass this dialog the first time through the loop.
        d = HostPortDialog(host=host, port=port, disconnectReason=disconnectReason,
                           settings=settings)
        host, port = d.run()
        if host is None or port is None:
            print "Could not start Dastard-commander without a valid host:port selection."
            return
        try:
            client = rpc_client.JSONClient((host, port))
        except socket.error:
            print "Could not connect to Dastard at %s:%d" % (host, port)
            continue
        print "Dastard is at %s:%d" % (host, port)

        dc = MainWindow(client, host, port)
        dc.show()

        retval = app.exec_()
        disconnectReason = dc.disconnectReason
        if not dc.reconnect:
            sys.exit(retval)


if __name__ == "__main__":
    main()
