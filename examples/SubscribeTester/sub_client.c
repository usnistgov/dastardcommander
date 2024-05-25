#include "zmq.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
  void *context = zmq_init(1);
  void *socket = zmq_socket(context, ZMQ_SUB);
  zmq_connect(socket, "tcp://localhost:5501");
  zmq_setsockopt(socket, ZMQ_SUBSCRIBE, "", 0);

  char string[1000] = "";
  const int flags=0;
  while(1) {
    zmq_msg_t in_msg;
    zmq_msg_init(&in_msg);
    zmq_msg_recv(&in_msg, socket, flags);
    int more = 0;
    size_t morelen = sizeof(more);
    zmq_getsockopt(socket, ZMQ_RCVMORE, &more, &morelen);
    int size = zmq_msg_size (&in_msg);
    memcpy(string, zmq_msg_data(&in_msg), size);
    zmq_msg_close(&in_msg);
    string[size] = 0;
    printf("%s", string);
    if (more) {
      printf("...");
    } else {
      printf("\n");
    }
  }
}
