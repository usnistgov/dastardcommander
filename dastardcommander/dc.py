#!/usr/bin/env python3

"""
dastardcommander (dc.py)

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
import os

from collections import OrderedDict, defaultdict
import numpy as np
# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QSettings, pyqtSlot
from PyQt5.QtWidgets import QFileDialog

# User code imports
from . import rpc_client
from . import status_monitor
from . import trigger_config
from . import writing
from . import projectors
from . import observe
from . import workflow
__version__ = '0.2.1'

# Here is how you try to import compiled UI files and fall back to processing them
# at load time via PyQt5.uic. But for now, with frequent changes, let's process all
# at load time.
# try:
#     from dc_ui import Ui_MainWindow
# except ImportError:
#     Ui_MainWindow, _ = PyQt5.uic.loadUiType("dc.ui")
#
# TODO: don't process ui files at run-time, but compile them.
# note we now use PyQt5.uic.loadUi, but the principle remains that compiling these would speed startup


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, rpc_client, host, port, parent=None):
        self.client = rpc_client
        self.client.setQtParent(self)
        self.host = host
        self.port = port

        QtWidgets.QMainWindow.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon('dc.png'))
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/dc.ui"), self)
        self.setWindowTitle("Dastard Commander %s    (connected to %s:%d)" % (__version__, host, port))
        self.reconnect = False
        self.disconnectReason = ""
        self.disconnectButton.clicked.connect(lambda: self.closeReconnect("disconnect button"))
        self.actionDisconnect.triggered.connect(
            lambda: self.closeReconnect("disconnect menu item"))
        self.startStopButton.clicked.connect(self.startStop)
        self.dataSourcesStackedWidget.setCurrentIndex(self.dataSource.currentIndex())
        self.actionLoad_Projectors_Basis.triggered.connect(self.loadProjectorsBasis)
        self.actionLoad_Mix.triggered.connect(self.loadMix)
        self.actionPop_out_Observe.triggered.connect(self.popOutObserve)
        self.pushButton_sendEdgeMulti.clicked.connect(self.sendEdgeMulti)
        self.pushButton_sendMix.clicked.connect(self.sendMix)
        self.pushButton_sendExperimentStateLabel.clicked.connect(self.sendExperimentStateLabel)
        self.pushButton_pauseExperimental.clicked.connect(self.handlePauseExperimental)
        self.pushButton_unpauseExperimental.clicked.connect(self.handleUnpauseExperimental)
        self.running = False
        self.sourceIsTDM = False
        self.cols = 0
        self.rows = 0
        self.streams = 0
        self.lanceroCheckBoxes = {}
        self.updateLanceroCardChoices()
        self.buildLanceroFiberBoxes(8)
        self.triggerTab = trigger_config.TriggerConfig(self.tabTriggering)
        self.triggerTab.client = self.client
        self.writingTab = writing.WritingControl(self.tabWriting, host)
        self.writingTab.client = self.client
        self.observeTab = observe.Observe(self.tabObserve, host=host)
        self.observeTab.client = self.client
        self.observeWindow = observe.Observe(host=host)
        self.observeWindow.client = self.client
        self.workflowTab = workflow.Workflow(self, parent=self.tabWorkflow)
        self.triggerTab.changedTriggerStateSig.connect(self.observeTab.resetIntegration)

        self.microscopes = []
        self.last_messages = defaultdict(str)
        self.channel_names = []
        self.channel_prefixes = set()
        self.triggerTab.channel_names = self.channel_names
        self.observeTab.channel_names = self.channel_names
        self.observeWindow.channel_names = self.channel_names
        self.triggerTab.channel_prefixes = self.channel_prefixes
        self.workflowTab.channel_names = self.channel_names
        self.workflowTab.channel_prefixes = self.channel_prefixes
        self.launchMicroscopeButton.clicked.connect(self.launchMicroscope)
        self.killAllMicroscopesButton.clicked.connect(self.killAllMicroscopes)
        self.tabWidget.setEnabled(False)
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
            print("Error processing status message [topic,msg]: %s, %s" % (
                topic, message))
            print("Error is: %s" % e)
            return

        quietTopics = set(["TRIGGERRATE", "NUMBERWRITTEN", "ALIVE", "EXTERNALTRIGGER"])
        if topic not in quietTopics or self.nmsg < 15:
            print("%s %5d: %s" % (topic, self.nmsg, d))

        if topic == "ALIVE":
            self.heartbeat(d)

        elif topic == "TRIGGERRATE":
            self.observeTab.handleTriggerRateMessage(d)
            self.observeWindow.handleTriggerRateMessage(d)

        # All other messages are ignored if they haven't changed
        elif not self.last_messages[topic] == message:
            if topic == "STATUS":
                self.updateStatusBar(d)
                self.observeTab.handleStatusUpdate(d)
                self.observeWindow.handleStatusUpdate(d)
                self._setGuiRunning(d["Running"], d["SourceName"])
                self.triggerTab.updateRecordLengthsFromServer(d["Nsamples"], d["Npresamp"])
                self.workflowTab.handleStatusUpdate(d)

                source = d["SourceName"]
                nchan = d["Nchannels"]
                self.sourceIsTDM = (source == "Lancero")
                if source == "Triangles":
                    self.dataSource.setCurrentIndex(0)
                    self.triangleNchan.setValue(nchan)
                elif source == "SimPulses":
                    self.dataSource.setCurrentIndex(1)
                    self.simPulseNchan.setValue(nchan)
                elif source == "Lancero":
                    self.dataSource.setCurrentIndex(2)
                elif source == "Roach":
                    self.dataSource.setCurrentIndex(3)
                elif source == "Abaco":
                    self.dataSource.setCurrentIndex(4)

            elif topic == "TRIGGER":
                self.triggerTab.handleTriggerMessage(d)

            elif topic == "WRITING":
                self.writingTab.handleWritingMessage(d)
                self.workflowTab.handleWritingMessage(d)
                self.observeTab.handleWritingMessage(d)

            elif topic == "TRIANGLE":
                self.triangleNchan.setValue(d["Nchan"])
                self.triangleSampleRate.setValue(d["SampleRate"])
                self.triangleMinimum.setValue(d["Min"])
                self.triangleMaximum.setValue(d["Max"])

            elif topic == "SIMPULSE":
                self.simPulseNchan.setValue(d["Nchan"])
                self.simPulseBaseline.setValue(d["Pedestal"])
                self.simPulseSampleRate.setValue(d["SampleRate"])
                self.simPulseSamplesPerPulse.setValue(d["Nsamp"])
                a = d["Amplitudes"]
                if a is None or len(a) == 0:
                    a = [10000.0]
                self.simPulseAmplitude.setValue(a[0])

            elif topic == "LANCERO":
                self.updateLanceroCardChoices(d["DastardOutput"]["AvailableCards"])
                mask = d["FiberMask"]
                for k, v in list(self.fiberBoxes.items()):
                    v.setChecked(mask & (1 << k))
                ns = d["DastardOutput"]["Nsamp"]
                if ns > 0 and ns <= 16:
                    self.nsampSpinBox.setValue(ns)

            elif topic == "ROACH":
                self.updateRoachSettings(d)

            elif topic == "ABACO":
                self.updateAbacoCardChoices(d["AvailableCards"])

            elif topic == "CHANNELNAMES":
                self.channel_names[:] = []   # Careful: don't replace the variable
                self.channel_prefixes.clear()
                for name in d:
                    self.channel_names.append(name)
                    prefix = name.rstrip("1234567890")
                    self.channel_prefixes.add(prefix)
                print("New channames: ", self.channel_names)
                if self.sourceIsTDM:
                    self.triggerTab.channelChooserBox.setCurrentIndex(2)
                else:
                    self.triggerTab.channelChooserBox.setCurrentIndex(1)
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

            elif topic == "TESMAP":
                self.observeTab.handleTESMap(d)
                self.observeWindow.handleTESMap(d)

            elif topic == "TESMAPFILE":
                self.observeTab.handleTESMapFile(d)
                self.observeWindow.handleTESMapFile(d)

            elif topic == "MIX":
                # We only permit setting a single, common mix value from DC, so
                # we have to convert a variety of mixes to a single representative value.
                try:
                    mix = d[1]
                    self.doubleSpinBox_MixFraction.setValue(mix)
                except Exception as e:
                    print("Could not set mix; selecting 0")
                    self.doubleSpinBox_MixFraction.setValue(0.0)

            elif topic == "EXTERNALTRIGGER":
                self.observeTab.handleExternalTriggerMessage(d)
                self.observeWindow.handleExternalTriggerMessage(d)

            else:
                print("%s is not a topic we handle yet." % topic)

        self.nmsg += 1
        self.last_messages[topic] = message

        # Enable the window once the following message types have been received
        require = ("TRIANGLE", "SIMPULSE", "LANCERO", "ABACO")
        allseen = True
        for k in require:
            if k not in self.last_messages:
                allseen = False
                break
        if allseen:
            self.fullyConfigured = True
            self.tabWidget.setEnabled(True)

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
            self.streams = data["Nchannels"]
            self.cols = data.get("Ncol", [])
            self.rows = data.get("Nrow", [])
            ndev = min(len(self.cols), len(self.rows))
            if ndev == 1:
                status += " (%d rows x %d cols)" % (self.rows[0], self.cols[0])
            elif ndev > 1:
                status += " ("
                for i in range(ndev):
                    status += "%d x %d" % (self.rows[i], self.cols[i])
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
        self.observeWindow.hide()  # prevents close hanging due to still visible observeWindow

    @pyqtSlot()
    def launchMicroscope(self):
        """Launch one instance of microscope.
        TODO: don't hard-wire in the location of the binary!"""
        try:
            if self.sourceIsTDM:
                c, r = self.cols[0], self.rows[0]
            else:
                c, r = 1, self.streams
                while r > 40:
                    c *= 2
                    r = (r+1) // 2
            args = ["microscope", "-c%d" % c, "-r%d" % r]
            if not self.sourceIsTDM:
                args.append("--no-error-channel")
            args.append("tcp://%s:%d" % (self.host, self.port+2))
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

    def updateRoachSettings(self, settings):
        rates = settings["Rates"]
        if rates is not None:
            rateguis = (self.roachFrameRateDoubleSpinBox_1,
                        self.roachFrameRateDoubleSpinBox_2)
            for r, rategui in zip(rates, rateguis):
                rategui.setValue(r)

        hosts = settings["HostPort"]
        if hosts is not None:
            ips = (self.roachIPLineEdit_1, self.roachIPLineEdit_2)
            ports = (self.roachPortSpinBox_1, self.roachPortSpinBox_2)
            for hostport, ipgui, portgui in zip(hosts, ips, ports):
                parts = hostport.split(":")
                if len(parts) == 2:
                    ipgui.setText(parts[0])
                    portgui.setValue(int(parts[1]))
                else:
                    print("Could not parse hostport='%s'" % hostport)

    @pyqtSlot()
    def toggledRoachDeviceActive(self):
        a1 = self.roachDeviceCheckBox_1.isChecked()
        a2 = self.roachDeviceCheckBox_2.isChecked()
        self.roachIPLineEdit_1.setEnabled(a1)
        self.roachPortSpinBox_1.setEnabled(a1)
        self.roachFrameRateDoubleSpinBox_1.setEnabled(a1)
        self.roachIPLineEdit_2.setEnabled(a2)
        self.roachPortSpinBox_2.setEnabled(a2)
        self.roachFrameRateDoubleSpinBox_2.setEnabled(a2)

    def updateLanceroCardChoices(self, cards=None):
        """Build the check boxes to specify which Lancero cards to use.
        cards is a list of integers: which cards are available on the sever"""

        layout = self.lanceroChooserLayout
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
            self.noLanceroLabel.show()
        else:
            self.noLanceroLabel.hide()
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

    def updateAbacoCardChoices(self, cards=None):
        """Build the check boxes to specify which Abaco cards to use.
        cards is a list of integers: which cards are available on the sever"""

        TEST_CARD_NUMBER = 3
        layout = self.abacoChooserLayout
        # Empty the layout
        while True:
            item = layout.takeAt(0)
            if item is None:
                break
            del item

        self.abacoCheckBoxes = {}
        if cards is None:
            cards = []
        if len(cards) == 0:
            self.noAbacoLabel.show()
        else:
            self.noAbacoLabel.hide()
            layout.addWidget(QtWidgets.QLabel("Card number:"), 0, 0)

        narrow = QtWidgets.QSizePolicy()
        narrow.setHorizontalStretch(2)
        wide = QtWidgets.QSizePolicy()
        wide.setHorizontalStretch(10)

        for i, c in enumerate(cards):
            checkText = "abaco %d" % c
            if c == TEST_CARD_NUMBER:
                checkText += " (test data)"
            cb = QtWidgets.QCheckBox(checkText)
            cb.setToolTip("Ring buffer shm:xdma%d_c2h_0_buffer exists" % c)
            cb.setChecked(True)
            cb.setSizePolicy(wide)
            self.abacoCheckBoxes[c] = cb
            layout.addWidget(cb, i+1, 0)

    def buildLanceroFiberBoxes(self, nfibers):
        """Build the check boxes to specify which fibers to use."""
        layout = self.lanceroFiberLayout
        self.fiberBoxes = {}
        for i in range(nfibers):
            box = QtWidgets.QCheckBox("%d" % (i+nfibers))
            layout.addWidget(box, i, 1)
            self.fiberBoxes[i+nfibers] = box

            box = QtWidgets.QCheckBox("%d" % i)
            layout.addWidget(box, i, 0)
            self.fiberBoxes[i] = box

        def setAll(value):
            for box in list(self.fiberBoxes.values()):
                box.setChecked(value)

        def checkAll():
            setAll(True)

        def clearAll():
            setAll(False)

        self.allFibersButton.clicked.connect(checkAll)
        self.noFibersButton.clicked.connect(clearAll)
        self.roachDeviceCheckBox_1.toggled.connect(self.toggledRoachDeviceActive)
        self.roachDeviceCheckBox_2.toggled.connect(self.toggledRoachDeviceActive)

        self.toggleParallelStreaming(self.parallelStreaming.isChecked())
        self.parallelStreaming.toggled.connect(self.toggleParallelStreaming)

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
            okay = self._stop()
            self._setGuiRunning(False)
            # I think we want to do this even if stop failed, because it's usually due to an already stopped source?
        else:
            okay = self._start()
            if okay:
                self._setGuiRunning(True)

    def _stop(self):
        okay, error = self.client.call("SourceControl.Stop", "")
        if not okay:
            print("Could not Stop data")
            return False
        print("Stopping Data")
        return True

    def _setGuiRunning(self, running, sourceName=""):
        self.running = running
        label = "Start Data"
        if running:
            label = "Stop Data"
            self.triggerTab.isTDM(self.sourceIsTDM)
        self.startStopButton.setText(label)
        self.dataSource.setEnabled(not running)
        self.dataSourcesStackedWidget.setEnabled(not running)
        self.tabTriggering.setEnabled(running)
        self.launchMicroscopeButton.setEnabled(running)
        if running:
            self.tabWidget.setCurrentWidget(self.tabTriggering)

        runningTDM = running and self.sourceIsTDM
        self.triggerTab.coupleFBToErrCheckBox.setEnabled(runningTDM)
        self.triggerTab.coupleErrToFBCheckBox.setEnabled(runningTDM)
        self.triggerTab.coupleFBToErrCheckBox.setChecked(False)
        self.triggerTab.coupleErrToFBCheckBox.setChecked(False)


    def _start(self):
        self.sourceIsTDM = False
        sourceID = self.dataSource.currentIndex()
        if sourceID == 0:
            return self._startTriangle()
        elif sourceID == 1:
            return self._startSimPulse()
        elif sourceID == 2:
            result = self._startLancero()
            if result:
                self.sourceIsTDM = True
            return result
        elif sourceID == 3:
            result = self._startRoach()
            return result
        elif sourceID == 4:
            result = self._startAbaco()
            return result
        else:
            raise ValueError("invalid sourceID. have {}, want 0,1,2,3 or 4".format(sourceID))

    def _startTriangle(self):
        config = {
            "Nchan": self.triangleNchan.value(),
            "SampleRate": self.triangleSampleRate.value(),
            "Max": self.triangleMaximum.value(),
            "Min": self.triangleMinimum.value(),
        }
        okay, error = self.client.call("SourceControl.ConfigureTriangleSource", config)
        if not okay:
            print("Could not ConfigureTriangleSource")
            return False
        okay, error = self.client.call("SourceControl.Start", "TRIANGLESOURCE")
        if not okay:
            print("Could not Start Triangle ")
            return False
        print("Starting Triangle")
        return True

    def _startSimPulse(self):
        a0 = self.simPulseAmplitude.value()
        amps = [a0, a0*0.8, a0*0.6]
        config = {
            "Nchan": self.simPulseNchan.value(),
            "SampleRate": self.simPulseSampleRate.value(),
            "Amplitudes": amps,
            "Pedestal": self.simPulseBaseline.value(),
            "Nsamp": self.simPulseSamplesPerPulse.value(),
        }
        okay, error = self.client.call("SourceControl.ConfigureSimPulseSource", config)
        if not okay:
            print("Could not ConfigureSimPulseSource")
            return False
        okay, error = self.client.call("SourceControl.Start", "SIMPULSESOURCE")
        if not okay:
            print("Could not Start SimPulse")
            return False
        print("Starting Sim Pulses")
        return True

    def _startLancero(self):
        mask = 0
        for k, v in list(self.fiberBoxes.items()):
            if v.isChecked():
                mask |= (1 << k)
        print("Fiber mask: 0x%4.4x" % mask)
        clock = 125
        if self.lanceroClock50Button.isChecked():
            clock = 50
        nsamp = self.nsampSpinBox.value()

        activate = []
        delays = []
        for k, v in list(self.lanceroCheckBoxes.items()):
            if v.isChecked():
                activate.append(k)
                delays.append(self.lanceroDelays[k].value())

        config = {
            "FiberMask": mask,
            "ClockMhz": clock,
            "CardDelay": delays,
            "Nsamp": nsamp,
            "ActiveCards": activate,
            "AvailableCards": [],   # This is filled in only by server, not us.
            "AutoRestart": self.checkBox_lanceroAutoRestart.isChecked()
        }
        print("START LANCERO CONFIG")
        print(config)
        okay, error = self.client.call(
            "SourceControl.ConfigureLanceroSource", config, errorBox=True)
        if not okay:
            return False
        okay, error = self.client.call(
            "SourceControl.Start", "LANCEROSOURCE", errorBox=True, throwError=False)
        if not okay:
            return False
        self.triggerTab.coupleFBToErrCheckBox.setEnabled(True)
        self.triggerTab.coupleErrToFBCheckBox.setEnabled(True)
        self.triggerTab.coupleFBToErrCheckBox.setChecked(False)
        self.triggerTab.coupleErrToFBCheckBox.setChecked(False)
        return True

    def _startRoach(self):
        config = {
            "HostPort": [],
            "Rates": []
        }
        for id in (1, 2):
            if not self.__dict__["roachDeviceCheckBox_%d" % id].isChecked():
                continue
            ipwidget = self.__dict__["roachIPLineEdit_%d" % id]
            portwidget = self.__dict__["roachPortSpinBox_%d" % id]
            ratewidget = self.__dict__["roachFrameRateDoubleSpinBox_%d" % id]
            hostport = "%s:%d" % (ipwidget.text(), portwidget.value())
            rate = ratewidget.value()
            config["HostPort"].append(hostport)
            config["Rates"].append(rate)
        okay, error = self.client.call("SourceControl.ConfigureRoachSource", config)
        if not okay:
            print ("Could not ConfigureRoachSource")
            return False
        okay, error = self.client.call("SourceControl.Start", "ROACHSOURCE")
        if not okay:
            print ("Could not Start ROACH")
            return False
        print ("Starting ROACH")
        return True

    def _startAbaco(self):
        activate = []
        for k, v in list(self.abacoCheckBoxes.items()):
            if v.isChecked():
                activate.append(k)

        config = {
            "ActiveCards": activate,
            "AvailableCards": [],   # This is filled in only by server, not us.
        }
        okay, error = self.client.call("SourceControl.ConfigureAbacoSource", config)
        if not okay:
            print("Could not ConfigureAbacoSource")
            return False
        okay, error = self.client.call("SourceControl.Start", "ABACOSOURCE")
        if not okay:
            print("Could not Start Abaco")
            return False
        print("Starting Abaco")
        return True

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
            for channelIndex, config in list(configs.items()):
                print("sending ProjectorsBasis for {}".format(channelIndex))
                okay, error = self.client.call(
                    "SourceControl.ConfigureProjectorsBasis", config, verbose=False, errorBox=False, throwError=False)
                if okay:
                    success_chans.append(channelIndex)
                else:
                    failures[channelIndex] = error
            result = "success on channelIndicies (not channelName): {}\n".format(
                sorted(success_chans)) + "failures:\n" + json.dumps(failures, sort_keys=True, indent=4)
            resultBox = QtWidgets.QMessageBox(self)
            resultBox.setText(result)
            resultBox.show()

    @pyqtSlot()
    def loadMix(self):
        options = QFileDialog.Options()
        if not hasattr(self, "lastdir_mix"):
            dir = os.path.expanduser("~/.cringe")
        else:
            dir = self.lastdir_mix
        fileName, _ = QFileDialog.getOpenFileName(
            self, "Find Projectors Basis file", dir,
            "Mix Files (*.npy);;All Files (*)", options=options)
        if fileName:
            self.lastdir_mix = os.path.dirname(fileName)
            print("opening: {}".format(fileName))
            mixFractions = np.load(fileName)
            mixFractions[np.isnan(mixFractions)] = 0
            print("mixFractions.shape = {}".format(mixFractions.shape))
            config = {"ChannelIndices":  np.arange(1, mixFractions.size*2, 2).tolist(),
                      "MixFractions": mixFractions.flatten().tolist()}
            okay, error = self.client.call(
                "SourceControl.ConfigureMixFraction", config, verbose=True, throwError=False)

    @pyqtSlot()
    def popOutObserve(self):
        self.observeWindow.show()

    @pyqtSlot()
    def sendEdgeMulti(self):
        # first send the trigger mesage for all channels
        config = {
            "ChannelIndicies": list(range(len(self.channel_names))),
            "EdgeMulti": self.checkBox_EdgeMulti.isChecked(),
            "EdgeRising": self.checkBox_EdgeMulti.isChecked(),
            "EdgeTrigger": self.checkBox_EdgeMulti.isChecked(),
            "EdgeMultiNoise": self.checkBox_EdgeMultiNoise.isChecked(),
            "EdgeMultiMakeShortRecords": self.checkBox_EdgeMultiMakeShortRecords.isChecked(),
            "EdgeMultiMakeContaminatedRecords": self.checkBox_EdgeMultiMakeContaminatedRecords.isChecked(),
            "EdgeMultiVerifyNMonotone": self.spinBox_EdgeMultiVerifyNMonotone.value(),
            "EdgeLevel": self.spinBox_EdgeLevel.value()
        }
        self.client.call("SourceControl.ConfigureTriggers", config)

        # Reset trigger on even-numbered channels if source is TDM and the relevant
        # check box ("Trigger on Error Channels") isn't checked.
        omitEvenChannels = (self.sourceIsTDM and not
                            self.checkBox_edgeMultiTriggerOnError.isChecked())
        if omitEvenChannels:
            config = {"ChannelIndicies": list(range(0, len(self.channel_names), 2))}
            self.client.call("SourceControl.ConfigureTriggers", config)

    @pyqtSlot()
    def sendMix(self):
        print("sendMIX***********")
        mixFraction = self.doubleSpinBox_MixFraction.value()
        channels = [i for i in range(1, len(self.channel_names), 2)]  # only odd channels get mix
        mixFractions = [mixFraction for _ in range(len(channels))]
        config = {
            "ChannelIndices": channels,
            "MixFractions": mixFractions
        }
        try:
            self.client.call("SourceControl.ConfigureMixFraction", config)
            print("experimental mix config")
            print(config)
        except Exception as e:
            print("Could not set mix: {}".format(e))

    @pyqtSlot()
    def sendExperimentStateLabel(self):
        config = {
            "Label": self.lineEdit_experimentStateLabel.text(),
        }
        self.client.call("SourceControl.SetExperimentStateLabel", config)

    @pyqtSlot()
    def handlePauseExperimental(self):
        config = {
            "Request": "Pause"
        }
        self.client.call("SourceControl.WriteControl", config)

    @pyqtSlot()
    def handleUnpauseExperimental(self):
        config = {
            "Request": "Unpause "+self.lineEdit_unpauseExperimentalLabel.text()
        }
        self.client.call("SourceControl.WriteControl", config)


class HostPortDialog(QtWidgets.QDialog):
    def __init__(self, host, port, disconnectReason, settings, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon('dc.png'))
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/host_port.ui"), self)
        self.hostName.setText(host)
        self.basePortSpin.setValue(port)
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

        host = self.hostName.text()
        port = self.basePortSpin.value()
        self.settings.setValue("host", host)
        self.settings.setValue("port", int(port))
        return (host, port)

def main():
    if sys.version_info.major <= 2:
        print("WARNING: *** Only Python 3 is supported. Python 2 no longer guaranteed to work. ***")
    settings = QSettings("NIST Quantum Sensors", "dastardcommander")

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
        # None, None indicates user cancelled the dialog.
        if host is None and port is None:
            return

        # One None is an invalid host:port pair
        if host is None or port is None or host == "" or port == "":
            print("Could not start dcom (Dastard Commander) without a valid host:port selection.")
            return
        try:
            client = rpc_client.JSONClient((host, port))
        except socket.error:
            print("Could not connect to Dastard at %s:%d" % (host, port))
            continue
        print("Dastard is at %s:%d" % (host, port))

        dc = MainWindow(client, host, port)
        dc.show()
        retval = app.exec_()
        disconnectReason = dc.disconnectReason
        if not dc.reconnect:
            sys.exit(retval)


if __name__ == "__main__":
    main()
