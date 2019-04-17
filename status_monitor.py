import time
import zmq
from PyQt5 import QtCore
import collections


class ZMQListener(QtCore.QObject):
    """Code suggested by https://wiki.python.org/moin/PyQt/Writing%20a%20client%20for%20a%20zeromq%20service"""

    message = QtCore.pyqtSignal(str, str)

    def __init__(self, host, port):

        QtCore.QObject.__init__(self)

        # Socket to talk to server
        context = zmq.Context()
        self.socket = context.socket(zmq.SUB)

        self.host = host
        self.baseport = port+1
        self.address = "tcp://%s:%d" % (self.host, self.baseport)
        self.socket.connect(self.address)
        print("Collecting updates from dastard at %s" % self.address)

        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self.messages_seen = collections.Counter()
        self.quit_once = False
        self.running = False

    def loop(self):
        if self.quit_once:
            raise ValueError("Cannot run a ZMQListener.loop more than once!")
        self.running = True
        while self.running:
            # Check socket for events, with 100 ms timeout (so this loop and
            # its thread can end quickly when self.running set to False)
            if self.socket.poll(100) == 0:
                continue

            [topic, contents] = self.socket.recv_multipart()
            topic = topic.decode()
            contents = contents.decode()
            self.messages_seen[topic] += 1
            self.message.emit(topic, contents)

        self.socket.close()
        self.quit_once = True
        print("ZMQListener quit cleanly")
