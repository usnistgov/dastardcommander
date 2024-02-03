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
import zmq

from collections import defaultdict
import numpy as np

# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QSettings, pyqtSlot, QCoreApplication
from PyQt5.QtWidgets import QFileDialog

# User code imports
from . import configure_level_triggers
from . import disable_hyperactive
from . import rpc_client
from . import status_monitor
from . import trigger_blocker
from . import trigger_config
from . import trigger_config_simple
from . import writing
from . import projectors
from . import observe
from . import workflow

__version__ = "0.2.8"


def csv2int_array(text, normalize=False):
    """Convert a string of numerical values separated by whitespace and/or commas to a list of int.
    Any words that cannot be converted will be ignored.
    
    If `normalize`, remove duplicates and sort the list numerically.
    """
    array = []
    words = text.replace(",", " ").split()
    for w in words:
        try:
            array.append(int(w))
        except ValueError:
            pass
    
    if normalize:
        array = list(set(array))
        array.sort()
    
    return array


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

QCoreApplication.setOrganizationName("Quantum Sensors Group")
QCoreApplication.setOrganizationDomain("nist.gov")
QCoreApplication.setApplicationName("DastardCommander")

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, rpc_client, host, port, settings, parent=None):
        self.client = rpc_client
        self.client.setQtParent(self)
        self.host = host
        self.port = port
        self.settings = settings

        QtWidgets.QMainWindow.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        PyQt5.uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/dc.ui"), self)
        self.setWindowTitle(
            "Dastard Commander %s    (connected to %s:%d)" % (__version__, host, port)
        )
        self.reconnect = False
        self.disconnectReason = ""
        self.disconnectButton.clicked.connect(
            lambda: self.closeReconnect("disconnect button")
        )
        self.actionDisconnect.triggered.connect(
            lambda: self.closeReconnect("disconnect menu item")
        )
        self.startStopButton.clicked.connect(self.startStop)
        self.dataSourcesStackedWidget.setCurrentIndex(self.dataSource.currentIndex())
        self.actionLoad_Projectors_Basis.triggered.connect(self.loadProjectorsBasis)
        self.actionLoad_Mix.triggered.connect(self.loadMix)
        self.actionPop_out_Observe.triggered.connect(self.popOutObserve)
        self.actionTDM_Autotune.triggered.connect(self.crateStartAndAutotune)
        self.actionLevel_Trig_Configure.triggered.connect(self.configLevelTrigs)
        self.actionDisable_Hyperactive_Chans.triggered.connect(self.disableHyperactive)
        self.pushButton_sendEdgeMulti.clicked.connect(self.sendEdgeMulti)
        self.pushButton_sendMix.clicked.connect(self.sendMix)
        self.pushButton_sendExperimentStateLabel.clicked.connect(
            self.sendExperimentStateLabel
        )
        self.pushButton_pauseExperimental.clicked.connect(
            self.handlePauseExperimental)
        self.pushButton_unpauseExperimental.clicked.connect(
            self.handleUnpauseExperimental
        )
        self.sourceIsRunning = False
        self.sourceIsTDM = False
        self.cols = 0
        self.rows = 0
        self.streams = 0
        self.samplePeriod = 0
        self.lanceroCheckBoxes = {}
        self.updateLanceroCardChoices()
        parallel = settings.value("parallelStream", True, type=bool)
        self.buildLanceroFiberBoxes(8, parallel)
        self.triggerTab = trigger_config.TriggerConfig(None, self.client)
        self.tabTriggering.layout().addWidget(self.triggerTab)

        self.triggerTabSimple = trigger_config_simple.TriggerConfigSimple(None, self)
        self.tabTriggeringSimple.layout().addWidget(self.triggerTabSimple)
        self.tabTriggeringSimple.layout().addStretch()

        self.phaseResetSamplesBox.editingFinished.connect(self.slotPhaseResetUpdate)
        self.phaseResetMultiplierBox.editingFinished.connect(self.slotPhaseResetUpdate)
        self.comboBox_AbacoUnwrapEnable.currentIndexChanged.connect(
            self.slotPhaseUnwrapComboUpdate
        )
        self.triggerTab.recordLengthSpinBox.valueChanged.connect(
            self.slotPhaseResetUpdate
        )

        self.writingTab = writing.WritingControl(None, host, self.client)
        self.tabWriting.layout().addWidget(self.writingTab)

        self.observeWindow = observe.Observe(parent=None, host=host, client=self.client)
        self.observeTab = observe.Observe(parent=None, host=host, client=self.client)
        self.tabObserve.layout().addWidget(self.observeTab)

        # Create a TriggerBlocker and let the relevant tabs/windows share access to it.
        self.triggerBlocker = trigger_blocker.TriggerBlocker()
        self.triggerTab.triggerBlocker = self.triggerBlocker
        self.triggerTabSimple.triggerBlocker = self.triggerBlocker
        self.observeWindow.triggerBlocker = self.triggerBlocker
        self.observeTab.triggerBlocker = self.triggerBlocker
        cdb = self.triggerTab.clearDisabledButton
        for tab in (self.triggerTab, self.observeTab):
            cdb.clicked.connect(tab.pushedClearDisabled)
        self.observeTab.blocklist_changed.connect(self.triggerTab.updateDisabledList)
        self.observeTab.block_channel.connect(self.triggerTab.blockTriggering)
        self.triggerTab.updateDisabledList()
        self.lastTriggerRateMessage = (-1, {})

        self.workflowTab = workflow.Workflow(self, parent=self.tabWorkflow)
        self.workflowTab.projectorsLoadedSig.connect(
            self.writingTab.checkBox_OFF.setChecked
        )

        self.microscopes = []
        self.last_messages = defaultdict(str)
        self.channel_names = []
        self.channel_prefixes = set()
        self.channel_indices = {}  # a map from channel number to index
        self.triggerTabSimple.channel_indices = self.channel_indices
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

        self.pushButton_initializeCrate.clicked.connect(self.crateInitialize)
        self.pushButton_startAndAutotune.clicked.connect(self.crateStartAndAutotune)

        self.phasePosPulses.clicked.connect(self.updateBiasText)
        self.phaseNegPulses.clicked.connect(self.updateBiasText)
        self.unwrapBiasCheck.clicked.connect(self.updateBiasText)

        self.quietTopics = set(
            ["TRIGGERRATE", "NUMBERWRITTEN", "EXTERNALTRIGGER", "DATADROP"]
        )  # TODO: add "ALIVE"?

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
        self.zmqthread.started.connect(self.zmqlistener.status_monitor_loop)
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
            print(
                "Error processing status message [topic,msg]: '%s', '%s'"
                % (topic, message)
            )
            print("Error is: %s" % e)
            return

        _suppress_after_number = 20
        if topic not in self.quietTopics or self.nmsg <= _suppress_after_number:
            print("%s %5d: %s" % (topic, self.nmsg, d))
        if self.nmsg == _suppress_after_number + 1:
            note = f"After message #{_suppress_after_number}, suppressing {self.quietTopics} messages."
            print(note)

        if topic == "ALIVE":
            self.heartbeat(d)

        elif topic == "CURRENTTIME":
            print("CurrentTime message: '%s'" % message)

        elif topic == "TRIGGERRATE":
            self.observeTab.handleTriggerRateMessage(d)
            self.observeWindow.handleTriggerRateMessage(d)
            self.lastTriggerRateMessage = (self.nmsg, d)

        # All other messages are ignored if they haven't changed
        elif not self.last_messages[topic] == message:
            if topic == "STATUS":
                is_running = d["Running"]
                self._setGuiRunning(is_running)
                self.triggerTab.updateRecordLengthsFromServer(
                    d["Nsamples"], d["Npresamp"]
                )
                self.triggerTabSimple.handleNsamplesNpresamplesMessage(
                    d["Nsamples"], d["Npresamp"]
                )
                self.workflowTab.handleStatusUpdate(d)

                source = d["SourceName"]
                nchan = d["Nchannels"]
                self.samplePeriod = d["SamplePeriod"]

                self.sourceIsTDM = source == "Lancero"
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
                if is_running:
                    groups_info = d["ChanGroups"]
                else:
                    groups_info = None
                self.updateStatusBar(is_running, source, groups_info)
                self.observeTab.handleStatusUpdate(is_running, source, groups_info)
                self.observeWindow.handleStatusUpdate(is_running, source, groups_info)

            elif topic == "TRIGGER":
                self.triggerTab.handleTriggerMessage(d)
                self.triggerTabSimple.handleTriggerMessage(d)

            elif topic == "GROUPTRIGGER":
                self.triggerTab.handleGroupTriggerMessage(d)

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
                self.activateUDPsources(d["HostPortUDP"])
                self.fillPhaseResetInfo(d)
                invertedChannels = csv2int_array(d["InvertChan"], normalize=True)
                invertText = ", ".join([str(c) for c in invertedChannels])
                self.invertedChanTextEdit.setPlainText(invertText)
                self.actionChange_Inverted_Chans.setChecked(False)

            elif topic == "CHANNELNAMES":
                # Careful: don't replace the variable
                self.channel_names[:] = []
                self.channel_prefixes.clear()
                self.channel_indices.clear()  # a map from channel numbers to indices
                for index, name in enumerate(d):
                    self.channel_names.append(name)
                    prefix = name.rstrip("1234567890")
                    self.channel_prefixes.add(prefix)
                    if prefix == "chan":
                        number = int(name[len(prefix):])
                        self.channel_indices[number] = index
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
                # self.workflowTab.handleNumberWritten(d)

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
                    print("Could not set mix; selecting 0 (exception: {})".format(e))
                    self.doubleSpinBox_MixFraction.setValue(0.0)

            elif topic == "EXTERNALTRIGGER":
                self.observeTab.handleExternalTriggerMessage(d)
                self.observeWindow.handleExternalTriggerMessage(d)

            elif topic == "STATELABEL":
                self.observeTab.ExperimentStateIncrementer.updateLabel(d)
                self.observeWindow.ExperimentStateIncrementer.updateLabel(d)

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

    def updateStatusBar(self, is_running, source_name, group_info):

        if is_running:
            sp = self.samplePeriod
            if sp < 1000:
                period = f"{sp} ns"
            elif sp < 10000:
                period = "{:.3f} µs".format(sp / 1000)
            elif sp < 100000:
                period = "{:.2f} µs".format(sp / 1000)
            elif sp < 1000000:
                period = "{:.1f} µs".format(sp / 1000)
            else:
                period = "{:.3f} ms".format(sp / 1e6)

            ngroups = len(group_info)
            nc_group0 = group_info[0]["Nchan"]
            nchan = np.sum([v["Nchan"] for v in group_info])
            if np.all([v["Nchan"] == nc_group0 for v in group_info]):
                status = f"{source_name} active: sample period {period}.  {ngroups} groups x {nc_group0} chans = {nchan} channels."
            else:
                status = f"{source_name} active: sample period {period}.  {ngroups} groups with {nchan} total channels."
        else:
            status = "Data source stopped."
        self.statusMainLabel.setText(status)

    def heartbeat(self, hb):
        # Keep window open another 5 seconds
        self.hbTimer.start(self.hbTimeout)

        mb = hb["DataMB"]
        hwmb = hb["HWactualMB"]
        t = float(hb["Time"])

        def color(c, bg=None):
            ss = "QLabel { color : %s; }" % c
            if bg is not None:
                ss = "QLabel { color : %s; background-color : %s }" % (c, bg)
            self.statusFreshLabel.setStyleSheet(ss)

        if mb <= 0:
            # No data is okay...unless server says it's running!
            if self.sourceIsRunning:
                self.statusFreshLabel.setText("no fresh data")
                color("white", bg="red")
            else:
                self.statusFreshLabel.setText("")

        elif t <= 0:
            self.statusFreshLabel.setText("%7.3f MB in 0 s??" % mb)
            color("red")
        else:
            rate = mb / t
            if hwmb == mb:
                self.statusFreshLabel.setText("%7.3f MB/s" % rate)
                color("green")
            else:
                hwrate = hwmb / t
                self.statusFreshLabel.setText(
                    "%7.3f MB/s received (%7.3f processed)" % (hwrate, rate)
                )
                color("orange")

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
        """Launch one instance of microscope. It must be on $PATH."""
        try:
            args = ["microscope"]
            if not self.sourceIsTDM:
                args.append("--no-error-channel")
            args.append("tcp://%s:%d" % (self.host, self.port + 2))
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
            rateguis = (
                self.roachFrameRateDoubleSpinBox_1,
                self.roachFrameRateDoubleSpinBox_2,
            )
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
            layout.addWidget(cb, i + 1, 0)
            sb = QtWidgets.QSpinBox()
            sb.setMinimum(0)
            sb.setMaximum(40)
            sb.setValue(1)
            sb.setSizePolicy(narrow)
            sb.setToolTip("Card delay for card %d" % c)
            self.lanceroDelays[c] = sb
            layout.addWidget(sb, i + 1, 1)

    def updateAbacoCardChoices(self, cards=None):
        """Build the check boxes to specify which Abaco cards to use.
        cards is a list of integers: which cards are available on the sever"""

        TEST_CARD_NUMBER = 3
        layout = self.shmChooserLayout
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
            layout.addWidget(cb, i + 1, 0)

    def activateUDPsources(self, sources):
        """Given sources=["localhost:4000"] or similar, find GUI entries that matches elements
        of the list. If none, change GUI entries (from top to bottom) to match. Activate the check
        box for all sources in the `sources` argument."""
        self.udpActive1.setChecked(False)
        self.udpActive2.setChecked(False)
        self.udpActive3.setChecked(False)
        self.udpActive4.setChecked(False)
        if sources is None:
            return
        unperturbed_guis = [1, 2, 3, 4]
        sources_to_insert = []
        if len(sources) > 4:
            print(
                "UDP sources '{}' is too long. Truncating to 4 sources".format(sources)
            )
            sources = sources[:4]

        localsynonyms = ("127.0.0.1", "localhost", "localhost.local")
        for text in sources:
            parts = text.split(":")
            if len(parts) != 2:
                print("Could not parse '{}' as host:port".format(text))
                return
            host, port = parts[0], int(parts[1])
            found = False
            for id in unperturbed_guis:
                guihost = self.__dict__["udpHost%d" % id].text()
                guiport = self.__dict__["udpPort%d" % id].value()
                if guiport != port:
                    continue
                if guihost == host or (
                    guihost in localsynonyms and host in localsynonyms
                ):
                    self.__dict__["udpActive%d" % id].setChecked(True)
                    found = True
                    unperturbed_guis.remove(id)
                    break
            if not found:
                sources_to_insert.append((host, port))
        for id, (host, port) in zip(unperturbed_guis, sources_to_insert):
            self.__dict__["udpActive%d" % id].setChecked(True)
            self.__dict__["udpHost%d" % id].setText(host)
            self.__dict__["udpPort%d" % id].setValue(port)

    def fillPhaseResetInfo(self, d):
        self.unwrapBiasCheck.setChecked(d["Bias"])
        if d["PulseSign"] >= 0:
            self.phasePosPulses.setChecked(True)
        else:
            self.phaseNegPulses.setChecked(True)
        self.updateBiasText()
        self.phaseResetSamplesBox.setValue(d["ResetAfter"])
        unwrap, dropBits = d["Unwrap"], d["RescaleRaw"]
        if unwrap and dropBits:
            index = AbacoUnwrapChoice.UNWRAP
        elif not unwrap and dropBits:
            index = AbacoUnwrapChoice.DROPBITS_ONLY
        elif not unwrap and not dropBits:
            index = AbacoUnwrapChoice.NODROPBITS
        else:
            # invalid combination; default to unwrap
            index = AbacoUnwrapChoice.UNWRAP
        self.comboBox_AbacoUnwrapEnable.setCurrentIndex(index)

    @pyqtSlot(int)
    def slotPhaseUnwrapComboUpdate(self, index):
        """When the phase unwrapping combo box changes (self.comboBox_AbacoUnwrapEnable),
        enable or disable all the GUI elements that control unwrapping parameters. Enable
        if changed to the AbacoUnwrapChoice.UNWRAP state; otherwise disable."""
        toenable = index == AbacoUnwrapChoice.UNWRAP
        for widget in (
            self.unwrapBiasCheck,
            self.phaseNegPulses,
            self.phasePosPulses,
            self.biasTextLabel,
            self.phaseResetSamplesBox,
            self.phaseResetMultiplierBox,
            self.phaseResetSamplesLabel,
            self.phaseResetMultiplierLabel,
            self.resetAfterLabel,
        ):
            widget.setEnabled(toenable)

    @pyqtSlot()
    def slotPhaseResetUpdate(self):
        sender = self.sender()
        if sender == self.phaseResetSamplesBox:
            ratio = (
                self.phaseResetSamplesBox.value()
                / self.triggerTab.recordLengthSpinBox.value()
            )
            self.phaseResetMultiplierBox.setValue(ratio)
        elif sender == self.phaseResetMultiplierBox:
            ns = (
                self.phaseResetMultiplierBox.value()
                * self.triggerTab.recordLengthSpinBox.value()
            )
            self.phaseResetSamplesBox.setValue(int(ns + 0.5))
        elif sender == self.triggerTab.recordLengthSpinBox:
            reclen = self.triggerTab.recordLengthSpinBox.value()
            ratio = self.phaseResetSamplesBox.value() / reclen
            self.phaseResetMultiplierBox.setValue(ratio)

    def buildLanceroFiberBoxes(self, nfibers, parallelStreaming):
        """Build the check boxes to specify which fibers to use."""
        layout = self.lanceroFiberLayout
        self.fiberBoxes = {}
        for i in range(nfibers):
            box = QtWidgets.QCheckBox("%d" % (i + nfibers))
            layout.addWidget(box, i, 1)
            self.fiberBoxes[i + nfibers] = box

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

        self.parallelStreaming.setChecked(parallelStreaming)
        if parallelStreaming:
            self.toggleParallelStreaming(self.parallelStreaming.isChecked())
        self.parallelStreaming.toggled.connect(self.toggleParallelStreaming)

    @pyqtSlot(bool)
    def toggleParallelStreaming(self, parallelStream):
        """Make the parallel streaming connection between boxes."""
        nfibers = len(self.fiberBoxes)
        npairs = nfibers // 2
        if parallelStream:
            for i in range(npairs):
                box1 = self.fiberBoxes[i]
                box2 = self.fiberBoxes[i + npairs]
                either = box1.isChecked() or box2.isChecked()
                box1.setChecked(either)
                box2.setChecked(either)
                box1.toggled.connect(box2.setChecked)
                box2.toggled.connect(box1.setChecked)
        else:
            for i in range(npairs):
                box1 = self.fiberBoxes[i]
                box2 = self.fiberBoxes[i + npairs]
                box1.toggled.disconnect()
                box2.toggled.disconnect()
        self.settings.setValue("parallelStream", parallelStream)

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
        if self.sourceIsRunning:
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

    def _setGuiRunning(self, running):
        was_running = self.sourceIsRunning
        self.sourceIsRunning = running
        label = "Start Data"
        if running:
            label = "Stop Data"
            self.triggerTab.isTDM(self.sourceIsTDM)
        self.startStopButton.setText(label)
        self.dataSource.setEnabled(not running)
        self.dataSourcesStackedWidget.setEnabled(not running)
        self.tabTriggering.setEnabled(running)
        self.launchMicroscopeButton.setEnabled(running)
        if running and not was_running:
            self.tabWidget.setCurrentWidget(self.tabTriggeringSimple)

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
            raise ValueError(
                "invalid sourceID. have {}, want 0,1,2,3 or 4".format(sourceID)
            )

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
        amps = [a0, a0 * 0.8, a0 * 0.6]
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
                mask |= 1 << k
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

        chansep_columns = 0
        chansep_cards = 0
        firstrow = 1
        if self.channels1kcardbutton.isChecked():
            chansep_cards = 1000
        if self.channels10kcard1kcolButton.isChecked():
            chansep_cards = 10000
            chansep_columns = 1000
            firstrow = self.firstRowSpinBox.value()

        config = {
            "FiberMask": mask,
            "ClockMHz": clock,
            "CardDelay": delays,
            "Nsamp": nsamp,
            "FirstRow": firstrow,
            "ChanSepCards": chansep_cards,
            "ChanSepColumns": chansep_columns,
            "ActiveCards": activate,
            "AvailableCards": [],  # This is filled in only by server, not us.
        }
        print("START LANCERO CONFIG")
        print(config)
        okay, error = self.client.call(
            "SourceControl.ConfigureLanceroSource", config, errorBox=True
        )
        if not okay:
            return False
        okay, error = self.client.call(
            "SourceControl.Start", "LANCEROSOURCE", errorBox=True, throwError=False
        )
        if not okay:
            return False
        self.triggerTab.coupleFBToErrCheckBox.setEnabled(True)
        self.triggerTab.coupleErrToFBCheckBox.setEnabled(True)
        self.triggerTab.coupleFBToErrCheckBox.setChecked(False)
        self.triggerTab.coupleErrToFBCheckBox.setChecked(False)
        return True

    def _startRoach(self):
        config = {"HostPort": [], "Rates": []}
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
            print("Could not ConfigureRoachSource")
            return False
        okay, error = self.client.call("SourceControl.Start", "ROACHSOURCE")
        if not okay:
            print("Could not Start ROACH")
            return False
        print("Starting ROACH")
        return True

    def _startAbaco(self):
        activate = []
        for k, v in list(self.abacoCheckBoxes.items()):
            if v.isChecked():
                activate.append(k)
        
        # Read the invertedChan list. Normalize it by making the list contain only unique and sorted values.
        # Update the GUI with the normalized list
        invertedChannels = csv2int_array(self.invertedChanTextEdit.toPlainText(), normalize=True)
        invertText = ", ".join([str(c) for c in invertedChannels])
        self.invertedChanTextEdit.setPlainText(invertText)

        if self.phasePosPulses.isChecked():
            pulsesign = +1
        else:
            pulsesign = -1
        unwrapBias = self.unwrapBiasCheck.isChecked()

        index = self.comboBox_AbacoUnwrapEnable.currentIndex()
        if index == AbacoUnwrapChoice.UNWRAP:
            unwrap, dropBits = True, True
        elif index == AbacoUnwrapChoice.DROPBITS_ONLY:
            unwrap, dropBits = False, True
        elif index == AbacoUnwrapChoice.NODROPBITS:
            unwrap, dropBits = False, False
        config = {
            "ActiveCards": activate,
            "AvailableCards": [],  # This is filled in only by server, not us.
            "HostPortUDP": [],
            # the following are fields of AbacoUnwrapOptions
            # but I can't nest them in the dict to make it more clear :()
            "Unwrap": unwrap,
            "ResetAfter": self.phaseResetSamplesBox.value(),
            "PulseSign": pulsesign,
            "Bias": unwrapBias,
            "RescaleRaw": dropBits,
            "InvertChan": invertedChannels,
        }

        for id in (1, 2, 3, 4):
            if not self.__dict__["udpActive%d" % id].isChecked():
                continue
            ipwidget = self.__dict__["udpHost%d" % id]
            portwidget = self.__dict__["udpPort%d" % id]
            hostport = "%s:%d" % (ipwidget.text(), portwidget.value())
            config["HostPortUDP"].append(hostport)

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
    def updateBiasText(self):
        if self.unwrapBiasCheck.isChecked():
            if self.phasePosPulses.isChecked():
                label = "Pos bias: [-.12, +.88]"
            else:
                label = "Neg bias: [-.88, +.12]"
        else:
            label = "No bias: [-.50, +.50]"
        self.biasTextLabel.setText(label)

    @pyqtSlot()
    def loadProjectorsBasis(self):
        if not hasattr(self, "lastdir"):
            startdir = os.path.expanduser("~")
        else:
            startdir = self.lastdir
        fileName = projectors.getFileNameWithDialog(qtparent=self, startdir=startdir)
        if fileName:
            self.lastdir = os.path.dirname(fileName)
            projectors.sendProjectors(self, fileName, self.channel_names, self.client)

    @pyqtSlot()
    def loadMix(self):
        options = QFileDialog.Options()
        if not hasattr(self, "lastdir_mix"):
            dir = os.path.expanduser("~/.cringe")
        else:
            dir = self.lastdir_mix
        fileName, _ = QFileDialog.getOpenFileName(
            self,
            "Find Projectors Basis file",
            dir,
            "Mix Files (*.npy);;All Files (*)",
            options=options,
        )
        if fileName:
            self.lastdir_mix = os.path.dirname(fileName)
            print("opening: {}".format(fileName))
            mixFractions = np.load(fileName)
            mixFractions[np.isnan(mixFractions)] = 0
            print("mixFractions.shape = {}".format(mixFractions.shape))
            config = {
                "ChannelIndices": np.arange(1, mixFractions.size * 2, 2).tolist(),
                "MixFractions": mixFractions.flatten().tolist(),
            }
            okay, error = self.client.call(
                "SourceControl.ConfigureMixFraction",
                config,
                verbose=True,
                throwError=False,
            )

    @pyqtSlot()
    def popOutObserve(self):
        self.observeWindow.show()

    @pyqtSlot()
    def sendEdgeMulti(self):
        # first send the trigger mesage for all channels
        config = {
            "ChannelIndices": list(range(len(self.channel_names))),
            "EdgeMulti": self.checkBox_EdgeMulti.isChecked(),
            "EdgeRising": self.checkBox_EdgeMulti.isChecked(),
            "EdgeTrigger": self.checkBox_EdgeMulti.isChecked(),
            "EdgeMultiNoise": self.checkBox_EdgeMultiNoise.isChecked(),
            "EdgeMultiMakeShortRecords": self.checkBox_EdgeMultiMakeShortRecords.isChecked(),
            "EdgeMultiMakeContaminatedRecords": self.checkBox_EdgeMultiMakeContaminatedRecords.isChecked(),
            "EdgeMultiVerifyNMonotone": self.spinBox_EdgeMultiVerifyNMonotone.value(),
            "EdgeLevel": self.spinBox_EdgeLevel.value(),
        }
        self.client.call("SourceControl.ConfigureTriggers", config)

        # Reset trigger on even-numbered channels if source is TDM and the relevant
        # check box ("Trigger on Error Channels") isn't checked.
        omitEvenChannels = (
            self.sourceIsTDM and not self.checkBox_edgeMultiTriggerOnError.isChecked()
        )
        if omitEvenChannels:
            config = {"ChannelIndices": list(range(0, len(self.channel_names), 2))}
            self.client.call("SourceControl.ConfigureTriggers", config)

    @pyqtSlot()
    def sendMix(self):
        print("sendMIX***********")
        mixFraction = self.doubleSpinBox_MixFraction.value()
        channels = [
            i for i in range(1, len(self.channel_names), 2)
        ]  # only odd channels get mix
        mixFractions = [mixFraction for _ in range(len(channels))]
        config = {"ChannelIndices": channels, "MixFractions": mixFractions}
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
        config = {"Request": "Pause"}
        self.client.call("SourceControl.WriteControl", config)

    @pyqtSlot()
    def handleUnpauseExperimental(self):
        config = {"Request": "Unpause " + self.lineEdit_unpauseExperimentalLabel.text()}
        self.client.call("SourceControl.WriteControl", config)

    def _cringeCommand(self, command):
        cringe_address = "localhost"
        cringe_port = 5509
        ctx = (
            zmq.Context()
        )  # just create a new context each time so we dont need to keep track of it
        cringe = ctx.socket(zmq.REQ)
        cringe.LINGER = 0  # ms
        cringe.RCVTIMEO = 30 * 1000  # ms
        cringe_addr = f"tcp://{cringe_address}:{cringe_port}"
        cringe.connect(cringe_addr)
        print(f"connect to cringe at {cringe_addr}")
        cringe.send_string(command)
        print(f"sent `{command}` to cringe")
        try:
            reply = (
                cringe.recv().decode()
            )  # this blocks until cringe replies, or until RCVTIMEO
            print(f"reply `{reply}` from cringe")
            message = f"reply={reply}"
            success = True
        except zmq.Again:
            message = f"Socket timeout, timeout = {cringe.RCVTIMEO/1000} s"
            print(message)
            success = False
        if not success:
            resultBox = QtWidgets.QMessageBox(self)
            resultBox.setText(f"Cringe Control Error\ncommand={command}\n{message}")
            resultBox.setWindowTitle("Cringe Control Error")
            # The above line doesn't work on mac, from qt docs "On macOS, the window
            # title is ignored (as required by the macOS Guidelines)."
            resultBox.show()

    def crateInitialize(self):
        self._cringeCommand("SETUP_CRATE")

    def crateStartAndAutotune(self):
        print("crateStartAndAutotune")
        if not self.sourceIsRunning:
            print("starting lancero")
            success = self._start()  # _startLancero wont set self.sourceIsTDM
            if not success:
                print(
                    "failed to start lancero, return early from crateStartAndAutotune"
                )
                return
            wait_ms = 500
        else:
            print("lancero already started, not starting")
            wait_ms = 0
        # wait a bit for dastard to get the lancero souce setup, then run full tune
        QtCore.QTimer.singleShot(wait_ms, lambda: self._cringeCommand("FULL_TUNE"))

    def channelIndicesAll(self):
        return list(range(len(self.channel_names)))

    def channelIndicesSignalOnly(self):
        return [
            i for (i, name) in enumerate(self.channel_names) if name.startswith("chan")
        ]

    def configLevelTrigs(self):
        configLevelDialog = configure_level_triggers.LevelTrigConfig(self)
        configLevelDialog.show()
        # host, port = d.run()
        # # None, None indicates user cancelled the dialog.
        print("Running the procedure to configure level triggers")

    def disableHyperactive(self):
        disableHyperDialog = disable_hyperactive.DisableHyperDialog(self)
        disableHyperDialog.show()
        print("Running the procedure to disable hyperactive channels")




class HostPortDialog(QtWidgets.QDialog):
    def __init__(self, host, port, disconnectReason, settings, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        PyQt5.uic.loadUi(
            os.path.join(os.path.dirname(__file__), "ui/host_port.ui"), self
        )
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
        print(
            "WARNING: *** Only Python 3 is supported. Python 2 no longer guaranteed to work. ***"
        )
    settings = QSettings("NIST Quantum Sensors", "dastardcommander")

    app = QtWidgets.QApplication(sys.argv)
    host = settings.value("host", "localhost", type=str)
    port = settings.value("port", 5500, type=int)
    disconnectReason = ""
    while True:
        # Ask user what host:port to connect to.
        # TODO: accept a command-line argument to specify host:port.
        # If given, we'll bypass this dialog the first time through the loop.
        d = HostPortDialog(
            host=host, port=port, disconnectReason=disconnectReason, settings=settings
        )
        host, port = d.run()
        # None, None indicates user cancelled the dialog.
        if host is None and port is None:
            return

        # One None is an invalid host:port pair
        if host is None or port is None or host == "" or port == "":
            print(
                "Could not start dcom (Dastard Commander) without a valid host:port selection."
            )
            return
        try:
            client = rpc_client.JSONClient((host, port))
        except socket.error:
            print("Could not connect to Dastard at %s:%d" % (host, port))
            continue
        print("Dastard is at %s:%d" % (host, port))

        dc = MainWindow(client, host, port, settings)
        dc.show()
        retval = app.exec_()
        disconnectReason = dc.disconnectReason
        if not dc.reconnect:
            sys.exit(retval)


class AbacoUnwrapChoice:
    UNWRAP = 0
    DROPBITS_ONLY = 1
    NODROPBITS = 2


if __name__ == "__main__":
    main()
