import time
import zmq
from PyQt5 import QtCore

class ZMQListener(QtCore.QObject):
    """Code suggested by https://wiki.python.org/moin/PyQt/Writing%20a%20client%20for%20a%20zeromq%20service"""

    message = QtCore.pyqtSignal(str, str)

    def __init__(self):

        QtCore.QObject.__init__(self)

        # Socket to talk to server
        context = zmq.Context()
        self.socket = context.socket(zmq.SUB)

        print "Collecting updates from dastard"
        self.socket.connect ("tcp://localhost:5501")

        self.topics = ("STATUS", "TRIGGER")
        for topic in self.topics:
            self.socket.setsockopt(zmq.SUBSCRIBE, topic)

        self.messages_seen = {t:0 for t in self.topics}
        self.quit_once = False

    def loop(self):
        if self.quit_once:
            raise ValueError("Cannot run a ZMQListener.loop more than once!")
        self.running = True
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        while self.running:
            evts = poller.poll(300) # wait 300 ms then timeout
            if len(evts) == 0:
                continue
            [topic, contents] = self.socket.recv_multipart()
            if topic in self.topics:
                self.messages_seen[topic] += 1
            if topic in ("STATUS", "TRIGGER"):
                self.message.emit(topic, contents)
        self.socket.close()
        self.quit_once = True
        print("ZMQListener quit cleanly")

    # def waitFirstMessages(self, topics):
    #     for t in topics:
    #         while self.messages_seen[t] <= 0:
    #             time.sleep(0.05)
