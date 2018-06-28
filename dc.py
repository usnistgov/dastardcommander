#!/usr/bin/env python

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
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QFileDialog

# User code imports
import rpc_client
import status_monitor
import trigger_config
import writing
import projectors
import observe

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
        self.host = host
        self.port = port

        QtWidgets.QMainWindow.__init__(self, parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.reconnect = False
        self.ui.disconnectButton.clicked.connect(self.closeReconnect)
        self.ui.actionDisconnect.triggered.connect(self.closeReconnect)
        self.ui.startStopButton.clicked.connect(self.startStop)
        self.ui.dataSourcesStackedWidget.setCurrentIndex(self.ui.dataSource.currentIndex())
        self.ui.actionLoad_Projectors_Basis.triggered.connect(self.loadProjectorsBasis)
        self.running = False
        self.lanceroCheckBoxes = {}
        self.updateLanceroCardChoices()
        self.buildLanceroFiberBoxes(8)
        self.tconfig = trigger_config.TriggerConfig(self.ui.tabTriggering)
        self.tconfig.client = self.client
        self.writing = writing.WritingControl(self.ui.tabWriting, host)
        self.writing.client = self.client
        self.observeTab = observe.Observe(self.ui.tabObserve)

        self.microscopes = []
        self.last_messages = defaultdict(str)
        self.channel_names = []
        self.channel_prefixes = set()
        self.tconfig.channel_names = self.channel_names
        self.observeTab.channel_names = self.channel_names
        self.tconfig.channel_prefixes = self.channel_prefixes
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
        self.hbTimer.timeout.connect(self.closeReconnect)
        self.hbTimeout = 5000  # that is, 5000 ms
        self.hbTimer.start(self.hbTimeout)

    def updateReceived(self, topic, message):
        try:
            d = json.loads(message)
        except Exception as e:
            print("Error processing status message: %s" % e)
            return

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
                self.tconfig.updateRecordLengthsFromServer(d["Nsamples"], d["Npresamp"])
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
                self.tconfig.handleTriggerMessage(d)

            elif topic == "WRITING":
                self.writing.handleWritingMessage(d)

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

            elif topic == "CHANNELNAMES":
                self.channel_names[:] = []   # Careful: don't replace the variable
                self.channel_prefixes.clear()
                for name in d:
                    self.channel_names.append(name)
                    prefix = name.rstrip("1234567890")
                    self.channel_prefixes.add(prefix)
                print "New channames: ", self.channel_names

            elif topic == "TRIGCOUPLING":
                self.tconfig.handleTrigCoupling(d)

            else:
                print("%s is not a topic we handle yet." % topic)

        print("%s %5d: %s" % (topic, self.nmsg, d))
        self.nmsg += 1
        self.last_messages[topic] = message

        # Enable the window once the following message types have been received
        require = ("TRIANGLE", "SIMPULSE", "LANCERO")
        all = True
        for k in require:
            if k not in self.last_messages:
                all = False
                break
        if all:
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

    # The following will cleanly close the zmqlistener.
    def closeEvent(self, event):
        self.zmqlistener.running = False
        self.zmqthread.quit()
        self.zmqthread.wait()

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

    def killAllMicroscopes(self):
        """Terminate all instances of microscope launched by this program."""
        while True:
            try:
                m = self.microscopes.pop()
                m.terminate()
            except IndexError:
                return

    def updateLanceroCardChoices(self, cards=[]):
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

    def closeReconnect(self):
        """Close the main window, but don't quit. Instead, ask for a new Dastard connection."""
        self.reconnect = True
        self.close()

    def close(self):
        """Close the main window and also the client connection to a Dastard process."""
        if self.client is not None:
            self.client.close()
        self.client = None
        QtWidgets.QMainWindow.close(self)

    def startStop(self):
        """Slot to handle pressing the Start/Stop data button."""
        if self.running:
            self._stop()
            self._setGuiRunning(False)
        else:
            self._start()
            self._setGuiRunning(True)

    def _stop(self):
        okay = self.client.call("SourceControl.Stop", "")
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
        self.tconfig.ui.coupleFBToErrCheckBox.setEnabled(enable)
        self.tconfig.ui.coupleErrToFBCheckBox.setEnabled(enable)
        self.tconfig.ui.coupleFBToErrCheckBox.setChecked(False)
        self.tconfig.ui.coupleErrToFBCheckBox.setChecked(False)

    def _start(self):
        sourceID = self.ui.dataSource.currentIndex()
        # These only make sense for Lancero
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
            okay = self.client.call("SourceControl.ConfigureTriangleSource", config)
            if not okay:
                print "Could not ConfigureTriangleSource"
                return
            okay = self.client.call("SourceControl.Start", "TRIANGLESOURCE")
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
        okay = self.client.call("SourceControl.ConfigureSimPulseSource", config)
        if not okay:
            print "Could not ConfigureSimPulseSource"
            return
        okay = self.client.call("SourceControl.Start", "SIMPULSESOURCE")
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
            "ActiveCards": activate,
            "AvailableCards": []   # This is filled in only by server, not us.
        }
        okay = self.client.call("SourceControl.ConfigureLanceroSource", config)
        if not okay:
            print "Could not ConfigureLanceroSource"
            return
        okay = self.client.call("SourceControl.Start", "LANCEROSOURCE")
        if not okay:
            print "Could not Start Lancero"
            return
        print "Starting Lancero device"
        self.tconfig.ui.coupleFBToErrCheckBox.setEnabled(True)
        self.tconfig.ui.coupleErrToFBCheckBox.setEnabled(True)
        self.tconfig.ui.coupleFBToErrCheckBox.setChecked(False)
        self.tconfig.ui.coupleErrToFBCheckBox.setChecked(False)

    def loadProjectorsBasis(self):
        options = QFileDialog.Options()
        if not hasattr(self,"lastdir"):
            dir = os.path.expanduser("~")
        else:
            dir = self.lastdir
        fileName, _ = QFileDialog.getOpenFileName(self,"Find Projectors Basis file", dir,"Model Files (*_model.h5);;All Files (*)", options=options)
        if fileName:
            self.lastdir = os.path.dirname(fileName)
            print("opening: {}".format(fileName))
            configs = projectors.getConfigs(fileName)
            print("Sending model for {} chans".format(len(configs)))
            success_chans = []
            failures = OrderedDict()
            for channum, config in configs.items():
                try:
                    self.client.call("SourceControl.ConfigureProjectorsBasis", config, verbose=False)
                    success_chans.append(channum)
                except Exception as ex:
                    failures[channum] = ex.args[0]

            print("success on chans: {}".format(success_chans))
            print("failures:")
            print( json.dumps(failures, sort_keys=True,indent=4) )


class HostPortDialog(QtWidgets.QDialog):
    def __init__(self, host, port, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.ui = Ui_HostPortDialog()
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
    host, port = "localhost", 5500

    while True:
        # Ask user what host:port to connect to.
        # TODO: accept a command-line argument to specify host:port.
        # If given, we'll bypass this dialog the first time through the loop.
        d = HostPortDialog(host=host, port=port)
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

        myapp = MainWindow(client, host, port)
        myapp.show()

        retval = app.exec_()
        if not myapp.reconnect:
            sys.exit(retval)


if __name__ == "__main__":
    main()
