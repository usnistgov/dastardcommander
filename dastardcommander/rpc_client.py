import json
import itertools
import socket

from PyQt5 import QtWidgets


class JSONClient:

    def __init__(self, addr, codec=json, qtParent=None):
        self._socket = socket.create_connection(addr)
        self._socket.settimeout(7.0)
        self._id_iter = itertools.count()
        self._codec = codec
        self._closed = False
        self.qtParent = qtParent

    def setQtParent(self, qtParent):
        """ let this know about Qt so it can pop-up error messages"""
        self.qtParent = qtParent

    def _message(self, name, params):
        return dict(id=next(self._id_iter),
                    params=[params],
                    method=name)

    def call(self, name, params, verbose=True, errorBox=True, throwError=False):
        if self._closed:
            print(f"{name}(...) ignored because JSON-RPC client is closed.")
            return None
            # This might seem like it should be impossible to reach, but it is possible
            # because signals like editingFinished can trigger slots when you try
            # to close a window while editing a QLineEdit (see issue #22).
            # If you skip this test, you get a segfault; this will be graceful.
        if verbose:
            print(f"SEND {name} {json.dumps(params)}")
        request = self._message(name, params)
        reqid = request.get('id')
        msg = self._codec.dumps(request)
        self._socket.sendall(msg.encode())

        # This will actually have to loop if resp is bigger than 4096 bytes
        response = self._socket.recv(4096)
        try:
            response = self._codec.loads(response.decode())
        except ValueError:  # This means RPC server is gone
            print("RPC server is missing.")
            self.qtParent.reconnect = True
            self.close()
            return None

        if response.get('id') != reqid:
            msg = f"JSON-RPC expected id={reqid}, received id={response.get('id')}: {response.get('error')}"
            raise ValueError(msg)

        if response.get('error') is not None:
            message = "Request: {}\n\nError: {}".format(request, response.get('error'))
            if verbose:
                print(message)
            if errorBox and self.qtParent is not None:
                resultBox = QtWidgets.QMessageBox(self.qtParent)
                resultBox.setText("DASTARD RPC Error\n" + message)
                resultBox.setWindowTitle("DASTARD RPC Error")
                # The above line doesn't work on mac, from qt docs "On macOS, the window
                # title is ignored (as required by the macOS Guidelines)."
                resultBox.show()
            elif throwError:
                raise Exception(message)
            else:
                print("PANIC unhandled response.get(error)")
        return response.get('result'), response.get("error")

    def close(self):
        if not self._closed:
            self._closed = True
            self._socket.close()
            if self.qtParent is not None:
                self.qtParent.close()
