import json
import itertools
import socket
DEBUG = True

class JSONClient(object):
    def __init__(self, addr, codec=json, qtParent = None):
        self._socket = socket.create_connection(addr)
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

    def call(self, name, params, verbose=True):
        if self._closed:
            print(("%s(...) ignored because JSON-RPC client is closed." % name))
            return None
            # This might seem like it should be impossible to reach, but it is possible
            # because signals like editingFinished can trigger slots when you try
            # to close a window while editing a QLineEdit (see issue #22).
            # If you skip this test, you get a segfault; this will be graceful.
        request = self._message(name, params)
        id = request.get('id')
        msg = self._codec.dumps(request)
        self._socket.sendall(msg.encode())
        if DEBUG:
            print("sending this message over RPC")
            print(msg)

        # This will actually have to loop if resp is bigger
        response = self._socket.recv(4096)
        response = self._codec.loads(response.decode())

        if DEBUG:
            print("response")
            print(response)

        if response.get('id') != id:
            raise Exception("expected id=%s, received id=%s: %s" %
                            (id, response.get('id'),
                             response.get('error')))

        if response.get('error') is not None:
            if verbose:
                print(("Yikes! Request is: ", request))
                print(("Reponse is: ", response))
            if self.qtParent is None:
                raise Exception(response.get('error'))
            else:
                em = QtWidgets.QErrorMessage(self.qtParent)
                em.showMessage("DASTARD Error: \n%s"%response.get('error'))

        return response.get('result')

    def close(self):
        self._closed = True
        self._socket.close()