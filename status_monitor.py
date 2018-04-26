import zmq
from PyQt5 import QtCore

class ZMQListener(QtCore.QObject):
    """Code suggested by https://wiki.python.org/moin/PyQt/Writing%20a%20client%20for%20a%20zeromq%20service"""

    message = QtCore.pyqtSignal(str)

    def __init__(self):

        QtCore.QObject.__init__(self)

        # Socket to talk to server
        context = zmq.Context()
        self.socket = context.socket(zmq.SUB)

        print "Collecting updates from dastard"
        self.socket.connect ("tcp://localhost:5501")

        # Subscribe to zipcode, default is NYC, 10001
        topic = "STATUS"
        self.socket.setsockopt(zmq.SUBSCRIBE, topic)

        self.running = True

    def loop(self):
        while self.running:
            [topic, contents] = self.socket.recv_multipart()
            if topic == "STATUS":
                self.message.emit(contents)
        print("ZMQListener quit cleanly")
