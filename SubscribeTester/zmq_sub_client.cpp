// From examples in https://github.com/booksbyus/zguide/tree/master/examples/C%2B%2B
//
//  Pubsub envelope subscriber
//
// Olivier Chamoux <olivier.chamoux@fr.thalesgroup.com>

#include "zhelpers.hpp"

int main () {
    //  Prepare our context and subscriber
    zmq::context_t context(1);
    zmq::socket_t subscriber (context, ZMQ_SUB);
    subscriber.connect("tcp://localhost:5501");
    subscriber.setsockopt( ZMQ_SUBSCRIBE, "", 0);

    while (1) {

		//  Read envelope with address
		std::string address = s_recv (subscriber);
		//  Read message contents
		std::string contents = s_recv (subscriber);

        std::cout << "[" << address << "] " << contents << std::endl;
    }
    return 0;
}
