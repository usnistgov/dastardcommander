CC    = gcc
RM     = rm -f
INCLUDE = -I/opt/local/include
CPPFLAGS = -Wall -O2 -g $(INCLUDE)
LDFLAGS = -L/opt/local/lib -lpthread -lzmq
SOURCES = $(wildcard *.cpp)
TARGETS = zmq_sub_client

all:	${TARGETS}

clean:
	${RM} *.o *~* ${TARGETS}

${TARGETS}:
	${CC} ${CPPFLAGS} -o $@ ${@:%=%.c} ${LDFLAGS}
