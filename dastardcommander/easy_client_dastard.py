from . import rpc_client_for_easy_client
import numpy
import zmq
import time
import collections
import json
import numpy as np

DEBUG = True
rpc_client_for_easy_client.DEBUG = False

SUMMARY_HEADER_DTYPE=np.dtype([("chan",np.uint16),("headerVersion",np.uint8),
     ("npresamples",np.uint32),("nsamples",np.uint32),("pretrig_mean","f4"),("peak_value","f4"),
     ("pulse_rms","f4"),("pulse_average","f4"),("residualStdDev","f4"),
     ("unixnano",np.uint64), ("trig frame",np.uint64)])

RECORD_HEADER_DTYPE = np.dtype([("chan",np.uint16),("headerVersion",np.uint8), ("dataTypeCode", np.uint8),
     ("npresamples",np.uint32),("nsamples",np.uint32),("samplePeriod","f4"),("voltsPerArb","f4"),
     ("unixnano",np.uint64), ("triggerFramecount",np.uint64)])

class EasyClientDastard():
    """This client will connect to a server's summary channels."""
    def __init__(self, host='localhost', baseport=5500, setupOnInit = True):
        self.host = host
        self.baseport = baseport
        self.context = zmq.Context()
        self.samplePeriod = None # learn this from first observed data packet
        self._restoredOldTriggerSettings = False
        if setupOnInit:
            self.setupAndChooseChannels()


    def _connectStatusSub(self):
        """ connect to the status update port of dastard """
        self.statusSub = self.context.socket(zmq.SUB)
        address = "tcp://%s:%d" % (self.host, self.baseport+1)
        self.statusSub.setsockopt(zmq.RCVTIMEO, 1000) # this doesn't seem to do anything
        self.statusSub.setsockopt( zmq.LINGER,      0 )
        self.statusSub.connect(address)
        print(("Collecting updates from dastard at %s" % address))
        self.statusSub.setsockopt_string(zmq.SUBSCRIBE, "")
        self.messagesSeen = collections.Counter()


    def _connectRPC(self):
        """ connect to the rpc port of dastard """
        self.rpc = rpc_client_for_easy_client.JSONClient((self.host, self.baseport))
        print(("Dastard is at %s:%d" % (self.host, self.baseport)))

    def _getStatus(self):
        self._sourceRecieved = False
        self._statusRecieved = False
        time.sleep(0.05) # these seem to help cringe be reliable
        self.rpc.call("SourceControl.SendAllStatus", "dummy")
        time.sleep(0.05) # these seem to help cringe be reliable
        tstart = time.time()
        while True:
            if time.time()-tstart > 2:
                raise Exception("took too long to get status")
            topic, contents = self.statusSub.recv_multipart()
            topic = topic.decode()
            contents = contents.decode()
            self.messagesSeen[topic] += 1
            self._handleStatusMessage(topic, contents)
            if DEBUG:
                print(f"messages seen so far = {self.messagesSeen}")
            if all([self.messagesSeen[t]>0 for t in ["STATUS", "LANCERO", "SIMPULSE"]]):
                if self.sourceName == "Lancero":
                    self.numRows = self.sequenceLength
                    self.numColumns = self.numChannels//(2*self.numRows)
                    assert self.numChannels%(2*self.numRows) == 0
                if self.sourceName == "SimPulses":
                    self.numColumns = 1
                    self.numRows = self.numChannels
                    self.linePeriod = "N/A"
                print("returned from _getStatus")
                return
        raise Exception(f"didn't get source and status messages, messagesSeen: {self.messagesSeen}")

    def _handleStatusMessage(self,topic, contents):
        if DEBUG:
            print(("topic=%s"%topic))
            print(contents)
        if topic in ["CURRENTTIME"]:
            if DEBUG:
                print(("skipping topic %s"%topic))
            return
        d = json.loads(contents)
        if DEBUG:
            print(d)
        if topic == "STATUS":
            self._statusRecieved = True
            self.numChannels = d["Nchannels"]
            self.sourceName = d["SourceName"]
            self._oldNSamples = d["Nsamples"]
            self._oldNPresamples = d["Npresamp"]
        if topic == "SIMPULSE" and self.sourceName=="SimPulses":
            if not DEBUG:
                raise Exception("dont use a SIMPULSE in non-debug mode")
            print("using SIMPULSE")
            self.nSamp = 2
            self.clockMhz = 125
            self.sequenceLength=self.numChannels
        if topic == "LANCERO" and self.sourceName=="Lancero":
            self.nSamp = d["DastardOutput"]["Nsamp"]
            self.clockMhz = d["DastardOutput"]["ClockMHz"]
            self.sequenceLength = d["DastardOutput"]["SequenceLength"]
            self.linePeriod = d["DastardOutput"]["Lsync"]
        if topic == "ABACO" and self.sourceName=="Abaco":
            self.nSamp = None
            self.numColumns = self.numChannels
            self.numRows = 1
            self.sequenceLength = None
            self.linePeriod = None
            self.clockMhz = None
        if topic == "TRIGGER":
            self._oldTriggerDict = d[0]


    def setupAndChooseChannels(self, streamFbChannels = True, streamErrorChannels = True):
        """ sets up the server to stream all Fb Channels or all error channels or both
        """
        self._connectRPC()
        self._connectStatusSub()
        self._getStatus()
        if self.sourceName == "Lancero":
            self.linePeriodSeconds = self.linePeriod/self.clockMhz
            self.samplePeriod = self.linePeriodSeconds*self.numRows
        elif self.sourceName == "Abaco":
            self.linePeriodSeconds = None
            self.samplePeriod = 8e-6

        print(self)

    @property
    def channelIndicies(self):
        return list(range(self.numChannels))




    def tdmChannelNumber(self, col, row):
        return 1+col*self.numRows+row

    def setMixToZero(self):
        self.setMix(0)

    def setMix(self, mixFractions):
        if len(numpy.shape(mixFractions))==0:  # voltage is a single number, make a array out of it, and set all channels to the same value
            mixFractions = numpy.ones((self.numColumns, self.numRows))*mixFractions
        if not numpy.all(numpy.shape(mixFractions) == (self.numColumns, self.numRows)):
            raise ValueError('mixFractions should either a number or a list/array with (numColumns, numRows) elements')
        config = {"ChannelIndices":  np.arange(1,self.numColumns*self.numRows*2,2).tolist(),
                  "MixFractions": mixFractions.flatten().tolist()}
        self.rpc.call("SourceControl.ConfigureMixFraction", config)

    def requestData(self, nsamples):
        config = {"N":int(nsamples)}
        result_npz_path = self.rpc.call("SourceControl.StoreRawDataBlock", nsamples)
        return result_npz_path


    def getNewData(self, npts):
        npz_filename = self.requestData(npts)
        # wait for the file to exist
        import os
        tstart = time.time()
        expect_s = self.samplePeriod*npts
        too_long_s = 1.1*expect_s+5
        while not os.path.isfile(npz_filename):
            time.sleep(0.1)
            elapsed_s = time.time()-tstart
            if elapsed_s>too_long_s:
                raise Exception("took too long")
        
        # now the file exists, lets open it
        data = np.load(npz_filename)        
        return data


    # emulate easyClientNDFB
    @property
    def ncol(self):
        return self.numColumns
    @property
    def nrow(self):
        return self.numRows
    @property
    def nsamp(self):
        return self.nSamp
    @property
    def num_of_samples(self):
        return self.nSamp
    @property
    def lsync(self):
        return self.linePeriod
    @property
    def sample_rate(self):
        return 1/self.samplePeriod


    def __repr__(self):
        return "EasyClientDastard {} columns X {} rows, linePeriod {}, clockMhz {}, nsamp {}".format(self.ncol,self.nrow,self.lsync,self.clockMhz, self.nsamp)

if __name__ == '__main__':
    if True:
        import pylab as plt
        plt.ion()
        plt.close("all")
        c = EasyClientDastard()
        sendModes = [0]
        sendModes = ["raw",0,1,2]
        for sendMode in sendModes:
            data = c.getNewData(delaySeconds=0.001,minimumNumPoints=6000,sendMode=sendMode)
            plt.figure()
            plt.plot(data[0,0,:,0],label="err (lastind 0)")
            plt.plot(data[0,0,:,1],label="fb (lastind 1)")
            plt.title("send mode = {}".format(sendMode))
            plt.xlabel("framecount")
            plt.ylabel("value")
            plt.legend()
        plt.show()

        if c.sourceName == "Lancero":
            mixFractions = [0,0.01,0.1,0.2,0.4,1]
            plt.figure()
            for mixFraction in mixFractions:
                c.setMixChannel(1,mixFraction)
                data = c.getNewData(.1)
                plt.plot(data[0,0,:,1],label="mixFrac {}".format(mixFraction))
            plt.legend()
            plt.ylabel("fb (lastind = 1)")
            plt.figure()
            for mixFraction in mixFractions:
                c.setMixChannel(1,.0001)
                data = c.getNewData(0.1)
                plt.plot(data[0,0,:,0],label="mixFrac {}".format(mixFraction))
            plt.ylabel("err (lastind = 0)")
            plt.legend()

        plt.show()
        eval(input())

    if True:
        # search for drops in one channel
        firsts = []
        c = EasyClientDastard()
        i=0
        ndrops=0
        while True:
            header,data = c.getMessage()
            if header["chan"]!=1:
                continue
            i+=1
            if i%100==0:
                print(i)
            firsts.append(header["triggerFramecount"])
            if np.sum(np.diff(firsts)<0)>0:
                print((np.sum(np.diff(firsts)<0), firsts))
            if np.sum(np.diff(firsts)>len(data))>ndrops:
                ndrops+=1
                print(("drop", ndrops, np.diff(firsts)/len(data)))