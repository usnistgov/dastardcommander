#!/usr/bin/env python3

"""
A stand-alone subscriber to listen to (and print) all messages published on a
ZMQ PUB-SUB pattern to port 5501 (or other, as given in command-line)

usage:

python zmq_sub_client.py [portnum]
"""

import sys
import zmq

host = "localhost:5501"
if len(sys.argv) > 1:
    host = sys.argv[1]

# Socket to talk to server
context = zmq.Context()
socket = context.socket(zmq.SUB)

print("Collecting updates from dastard server...")
socket.connect(f"tcp://{host}")

# for topicfilter in ("TRIGGER", "STATUS"):
#     socket.setsockopt_string(zmq.SUBSCRIBE, topicfilter)
socket.setsockopt_string(zmq.SUBSCRIBE, "")

total_value = 0
while True:
    message = socket.recv_multipart()
    if len(message) == 2:
        topic, messagedata = message
        print(topic, messagedata)
    else:
        print("WARNING: message of length {} is {}".format(len(message), message))
