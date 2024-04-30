import os
import time
import numpy as np
import struct
import PyQt5
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot, pyqtSignal
from . import status_monitor


class LevelTrigConfig(QtWidgets.QDialog):
    """
    A QDialog box that helps the user to configure level trigger settings for each channel.

    First the user says whether pulses are positive- or negative-going and how far from the
    baseline the trigger should be set.

    Then after user pushes "Start", auto triggers are turned on, the baseline levels for each
    channel are estimated, and then auto triggers are turned off and the level triggers are
    turned on.
    """

    header_fmt = "<HBBIIffQQ"
    data_fmt = ["b", "B", "<h", "<H", "<i", "<I", "<q", "<Q"]

    dataComplete = pyqtSignal()

    def __init__(self, parent=None):
        self.dcom = parent
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        uifile = os.path.join(os.path.dirname(__file__), "ui/level_trigger_config.ui")
        PyQt5.uic.loadUi(uifile, self)

        self.textBrowser.setReadOnly(True)
        self.zmqlistener = None
        self.zmqthread = None
        self.startButton.clicked.connect(self.startConfiguration)
        self.dataComplete.connect(self.finishConfiguration)

    @pyqtSlot()
    def startConfiguration(self):
        """The Start button causes this to run.

        It starts auto triggering (50 ms delay) and launches a thread to monitor the data records
        being generated."""
        self.positivePulseButton.setDisabled(True)
        self.negativePulseButton.setDisabled(True)
        self.levelSpinBox.setDisabled(True)
        self.startButton.setDisabled(True)

        threshold = self.levelSpinBox.value()
        self.recordsPerChan = 40

        self.cursor = self.textBrowser.textCursor()
        self.cursor.insertText(f"Configuring level triggers at (baseline{threshold:+d}) ...\n")
        self.save_quiet = "TRIGGER" in self.dcom.quietTopics
        if not self.save_quiet:
            self.dcom.quietTopics.add("TRIGGER")
            print("Will suppress printing of TRIGGER status until level triggers are configured.")

        self.cursor.insertText("1) Stopping all triggers.\n")
        # prev_trig_state = self.dcom.triggerTab.trigger_state.copy()
        if not self.turnOffAllTriggers():
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        self.cursor.insertText("2) Turning on 50 ms autotriggers.\n")
        channels_to_configure = self.dcom.triggerTabSimple.channelIndicesSignalOnly(exclude_blocked=True)
        if not self.startAutoTriggers(channels_to_configure):
            self.cursor.insertText("X  Failed: no channels known.\n")
            return

        # 3) Collect baseline level data
        self.cursor.insertText("3) Collecting baseline data (may take several seconds).\n")
        self.launchRecordMonitor(channels_to_configure)

    def launchRecordMonitor(self, channels_to_configure):
        positive = self.positivePulseButton.isChecked()
        self.channels_seen = {
            id: BaselineFinder(positive, self.recordsPerChan) for id in channels_to_configure
        }
        self.nchanIncomplete = len(channels_to_configure)
        self.progressBar.setMaximum(self.recordsPerChan * self.nchanIncomplete)
        self.zmqthread = QtCore.QThread()
        self.zmqlistener = status_monitor.ZMQListener(self.dcom.host, 1 + self.dcom.port)
        self.zmqlistener.pulserecord.connect(self.updateReceived)

        self.zmqlistener.moveToThread(self.zmqthread)
        self.zmqthread.started.connect(self.zmqlistener.data_monitor_loop)
        QtCore.QTimer.singleShot(0, self.zmqthread.start)

    @pyqtSlot()
    def finishConfiguration(self):
        """This slot is called when enough data has been collected to estimate all baselines.

        It computes the per-channel baseline level and then sets each channel's level appropriately.
        """

        # 4) Set level triggers (but turn them off first)
        self.cursor.insertText("4) Done with baseline data.  Stopping all triggers.\n")
        self.turnOffAllTriggers()
        self.cursor.insertText("5) Sending all level triggers\n")
        positive = self.positivePulseButton.isChecked()
        threshold = self.levelSpinBox.value()
        if not positive:
            threshold = -threshold
        for idx, blf in self.channels_seen.items():
            level = int(0.5 + blf.baseline() + threshold)
            ts = {
                "ChannelIndices": [idx],
                "AutoTrigger": False,
                "EdgeTrigger": False,
                "LevelTrigger": True,
                "LevelRising": positive,
                "LevelLevel": level,
            }
            self.dcom.client.call("SourceControl.ConfigureTriggers", ts)
            time.sleep(0.01)

        if not self.save_quiet:
            delay = 5000  # ms
            QtCore.QTimer.singleShot(delay, self.endSilentTRIGGER)
        self.cursor.insertText("Done! You may close this window.\n")

    @pyqtSlot()
    def endSilentTRIGGER(self):
        """Make TRIGGER messages non-quiet again (slot to run after a delay)."""
        self.dcom.quietTopics.remove("TRIGGER")

    @pyqtSlot()
    def done(self, dialogCode):
        """Cleanly close the zmqlistener before closing the dialog."""
        if self.zmqlistener is not None:
            self.zmqlistener.running = False
        if self.zmqthread is not None:
            self.zmqthread.quit()
            self.zmqthread.wait()
        super().done(dialogCode)

    def turnOffAllTriggers(self):
        """Configure all triggers to be completely off."""
        ids = self.dcom.channelIndicesAll()
        if len(ids) == 0:
            return False
        config = {
            "ChannelIndices": ids,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True

    def startAutoTriggers(self, channels_to_configure):
        """
        Start 50 ms autotriggers for the specified channels (these are channel indices).
        All other triggers are turned off.
        """
        if len(channels_to_configure) == 0:
            return False
        config = {
            "ChannelIndices": channels_to_configure,
            "AutoTrigger": True,
            "AutoDelay": 50000000,
        }
        self.dcom.client.call("SourceControl.ConfigureTriggers", config)
        return True

    @pyqtSlot(bytes, bytes)
    def updateReceived(self, header, data_message):
        """
        Slot to handle one data record for one channel.

        It ingests the data and feeds it to the BaselineFinder object for the channel.
        """
        try:
            values = struct.unpack(self.header_fmt, header)
            chanidx = values[0]
            blf = self.channels_seen[chanidx]
            if blf.completed:
                return

            typecode = values[2]
            data_fmt = self.data_fmt[typecode]
            # nsamp = values[4]
            data = np.frombuffer(data_message, dtype=data_fmt)
            blf.newValues(data)
            self.progressBar.setValue(self.progressBar.value() + 1)
            if blf.completed:
                self.nchanIncomplete -= 1
            if self.nchanIncomplete <= 0:
                self.dataComplete.emit()

        except Exception as e:
            print(f"Error processing pulse record is: {e}")
            return


class BaselineFinder:
    """
    An object to estimate the baseline of a channel's data.

    Usage:
    * Call `bf=BaseLineFinder(positivePulses=True)` to set up a finder for positive-going pulses,
        or with the argument False for negative-going pulses.
    * Call `bf.newValues(data)` to add a new data record `data` to the history.
    * Call `B=bf.baseline()` to estimate the baseline and return it.
    * Check `bf.completed` to see if a sufficient amount of data has been acquired.

    Algorithm:
        For each record, store the median data value. When we have enough (set by the constructor's
    `recordsRequired` optional argument), the answer is the lowest or highest median seen so far
    for positive- or negative-going pulses, respectively.

        There might be a lot of room to improve this, but it seems like a sensible starting point.
    I want it to work well when we are able to stop pulses, but still work okay even when we aren't.
    My thinking is that if there are no pulses, min(median) will be only slightly biased to low values
    by use of the minimum operation, because the median fluctuates only slightly. While if there
    ARE pulses, the minimum will allow us to turn immediately to the records with no residual pulse
    energy, or as close as we can get.
    """

    def __init__(self, positivePulses=True, recordsRequired=40):
        self.positivePulses = positivePulses
        self.recordsRequired = recordsRequired
        self.medians = []
        self.completed = False

    def newValues(self, data):
        data = np.asarray(data, dtype=np.uint16)
        median = np.median(data)

        if median > 65535 or median < 0:
            median %= 65536
        assert median >= 0

        self.medians.append(median)
        if len(self.medians) >= self.recordsRequired:
            self.completed = True

    def baseline(self):
        if self.positivePulses:
            return np.min(self.medians)
        return np.max(self.medians)
