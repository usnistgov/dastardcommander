import json

import itertools, socket

class JSONClient(object):

    def __init__(self, addr, codec=json):
        self._socket = socket.create_connection(addr)
        self._id_iter = itertools.count()
        self._codec = codec
        self._closed = False

    def _message(self, name, params):
        return dict(id=next(self._id_iter),
                    params=[params],
                    method=name)

    def call(self, name, params, verbose=True):
        if self._closed:
            raise Exception("call after socket closed")
            # this doesn't seem like it should be possible to reach
            # but I've seen a few errors that look like we're trying to send
            # after the socket is closed, and segfault, this will at least be graceful
        request = self._message(name, params)
        id = request.get('id')
        msg = self._codec.dumps(request)
        self._socket.sendall(msg.encode())

        # This will actually have to loop if resp is bigger
        response = self._socket.recv(4096)
        response = self._codec.loads(response.decode())

        if response.get('id') != id:
            raise Exception("expected id=%s, received id=%s: %s"
                            %(id, response.get('id'),
                              response.get('error')))

        if response.get('error') is not None:
            if verbose:
                print "Yikes! Request is: ", request
                print "Reponse is: ", response
            raise Exception(response.get('error'))

        return response.get('result')

    def close(self):
        self._socket.close()
        self._closed = True
