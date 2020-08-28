import h5py
import numpy as np
import base64
from collections import OrderedDict
import json

import PyQt5
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QFileDialog
#  0 -  3  Version = 1          (uint32)
#  4       'G'                  (byte)
#  5       'F'                  (byte)
#  6       'A'                  (byte)
#  7       0                    (byte)
#  8 - 15  number of rows       (int64)
# 16 - 23  number of columns    (int64)
# 24 - 31  0                    (int64)
# 32 - 39  0                    (int64)
# 40 - ..  matrix data elements (float64)
#          [0,0] [0,1] ... [0,ncols-1]
#          [1,0] [1,1] ... [1,ncols-1]
#          ...
#          [nrows-1,0] ... [nrows-1,ncols-1]


def toMatBase64(array):
    """
    returns s,v
    s - a base64 encoded string containing the bytes in a format compatible with
    gonum.mat.Dense.MarshalBinary, header version 1
    v - the value that was base64 encoded, is of a custom np.dtype specific to the length of the projectors
    array - an np.array with dtype float64 (or convertable to float64)
    """
    nrow, ncol = array.shape
    dt = np.dtype([('version', np.uint32), ('magic', np.uint8, (4,)), ("nrow", np.int64),
                   ("ncol", np.int64), ("zeros", np.int64, 2), ("data", np.float64, nrow*ncol)])
    a = np.array([(1, [ord("G"), ord("F"), ord("A"), 0], nrow, ncol, [0, 0], array.ravel())], dt)
    s_bytes = base64.b64encode(a)
    s = s_bytes.decode(encoding="ascii")
    return s, a[0]


def getConfigs(filename, channelNames):
    """
    returns an OrderedDict mapping channel number to a dict for use in calling
    self.client.call("SourceControl.ConfigureProjectorsBasis", config)
    to set Projectors and Bases
    extracts the channel numbers and projectors and basis from the h5 file
    filename - points to a _model.hdf5 file created by Pope
    """
    nameNumberToIndex = getNameNumberToIndex(channelNames)
    out = OrderedDict()
    if not h5py.is_hdf5(filename):
        print("{} is not a valid hdf5 file")
        return out
    h5 = h5py.File(filename, "r")
    for key in list(h5.keys()):
        nameNumber = int(key)
        channelIndex = nameNumberToIndex[nameNumber]
        projectors = h5[key]["svdbasis"]["projectors"][()]
        basis = h5[key]["svdbasis"]["basis"][()]
        rows, cols = projectors.shape
        # projectors has size (n,z) where it is (rows,cols)
        # basis has size (z,n)
        # coefs has size (n,1)
        # coefs (n,1) = projectors (n,z) * data (z,1)
        # modelData (z,1) = basis (z,n) * coefs (n,1)
        # n = number of basis (eg 3)
        # z = record length (eg 4)
        nBasis = rows
        recordLength = cols
        if nBasis > recordLength:
            print("projectors transposed for dastard, fix projector maker")
            config = {
                "ChannelIndex": channelIndex,
                "ProjectorsBase64": toMatBase64(projectors.T)[0],
                "BasisBase64": toMatBase64(basis.T)[0],
            }
        else:
            config = {
                "ChannelIndex": channelIndex,
                "ProjectorsBase64": toMatBase64(projectors)[0],
                "BasisBase64": toMatBase64(basis)[0],
            }
        out[nameNumber] = config
    return out


# dastard channelNames go from chan1 to chanN and err1 to errN
# we need to mape from channelName to channelIndex (0-2N-1)
def getNameNumberToIndex(channelNames):
    nameNumberToIndex = {}
    for (i, name) in enumerate(channelNames):
        if not name.startswith("chan"):
            continue
        nameNumber = int(name[4:])
        nameNumberToIndex[nameNumber] = i
        # for now since we only use this with lancero sources, error for non-odd index
        # if i % 2 != 1:
        #     raise Exception(
        #         "all fb channelIndicies on a lancero source are odd, we shouldn't load projectors for even channelIndicies")
    return nameNumberToIndex
#
# def remapConfigs(configs0, channelNames):
#     nameNumberToIndex = getNameNumberToIndex(channelNames)
#     configs = {}
#     for (nameNumber,config) in configs0.items():
#         configs[nameNumberToIndex[nameNumber]] = config
#     return configs


def getFileNameWithDialog(qtparent, startdir):
    options = QFileDialog.Options()
    fileName, _ = QFileDialog.getOpenFileName(
        qtparent, "Find Projectors Basis file", startdir,
        "Model Files (*_model.hdf5);;All Files (*)", options=options)
    return fileName


def sendProjectors(qtparent, fileName, channel_names, client):
        print("sendProjectors: opening: {}".format(fileName))
        configs = getConfigs(fileName, channel_names)
        print("sendProjectors: Sending model for {} chans".format(len(configs)))
        success_chans = []
        failures = OrderedDict()
        n_expected = np.sum([s.startswith("chan") for s in channel_names])
        for channelIndex, config in list(configs.items()):
            # print("sending ProjectorsBasis for {}".format(channelIndex))
            okay, error = client.call(
                "SourceControl.ConfigureProjectorsBasis", config, verbose=False, errorBox=False, throwError=False)
            if okay:
                success_chans.append(channelIndex)
            else:
                failures[channelIndex] = error

        success = len(failures) == 0 and len(success_chans) == n_expected
        result = "success on channelIndicies (not channelName): {}\n".format(
        sorted(success_chans)) + "failures:\n" + json.dumps(failures, sort_keys=True, indent=4)
        if not success:
            resultBox = QtWidgets.QMessageBox(qtparent)
            resultBox.setText(result)
            resultBox.show()
        print(result)
        return success 