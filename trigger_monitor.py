# This is a sketch of how a popepipe_zmq<->spec interface
# would work
# it is not functional

import zmq
import numpy as np
import time
from collections import OrderedDict, deque
PORT = 5504

ctx = zmq.Context() # context is required to create zmq socket
socket = zmq.Socket(ctx, zmq.SUB) # make a subscriber socket
socket.connect ("tcp://localhost:%s" % PORT) # connect to the server
socket.set_hwm(10000) # set the recieve side message buffer limit
socket.setsockopt(zmq.SUBSCRIBE, "") # subscribe to all message, since all start with ""

dtype_header=np.dtype([("chan",np.uint16),("header version",np.uint8),
     ("npresamples",np.uint32),("nsamples",np.uint32),("pretrig_mean","f4"),("peak_value","f4"),
     ("pulse_rms","f4"),("pulse_average","f4"),("residualStdDev","f4"),
     ("unixnano",np.uint64), ("trig frame",np.uint64)])



def add_counts(counts):
    while True:
        # read all available message, return when none are availble
        try:
            m = socket.recv_multipart(flags=zmq.NOBLOCK)
            header = np.frombuffer(m[0],dtype_header)[0]
            chan = header["chan"]
            unixnano = header["unixnano"]
            d = counts.get(chan,deque())
            d.append(unixnano)
            counts[chan]=d
        except zmq.ZMQError:
            break
    return counts

def nowNano():
    return int(round(time.time()*1e9))

def clearBefore(d, t0nano):
    removed = 0
    while len(d)>0:
        t = v.pop()
        if d>t0nano:
            d.appendleft(t)
            break
        removed+=1
    return removed



counts = OrderedDict()
tloNano = int(np.ceil(time.time())*1e9)
thiNano = tloNano+1000000000
thiPlusBuffer = thiNano*1e-9+0.05 # 50 ms buffer
while time.time()<thiPlusBuffer:
    print(time.time()-thiPlusBuffer)
    add_counts(counts)
    time.sleep(0.001)
    print("end",time.time()-thiPlusBuffer)


# n=clearBefore(counts[0],t0nano)
