#!/usr/bin/env python

"""
A stand-alone subscriber to listen to (and print) all messages published on a
ZMQ PUB-SUB pattern to port 5501 (or other, as given in command-line)

usage:

python zmq_sub_client.py [portnum]
"""

import sys
import zmq

port = "5501"
if len(sys.argv) > 1:
    port =  sys.argv[1]
    int(port)

# Socket to talk to server
context = zmq.Context()
socket = context.socket(zmq.SUB)

print "Collecting updates from dastard server..."
socket.connect ("tcp://localhost:%s" % port)

# for topicfilter in ("TRIGGER", "STATUS"):
#     socket.setsockopt(zmq.SUBSCRIBE, topicfilter)
socket.setsockopt(zmq.SUBSCRIBE, "")

# Process 5 updates
total_value = 0
while True:
    topic, messagedata = socket.recv_multipart()
    print topic, messagedata