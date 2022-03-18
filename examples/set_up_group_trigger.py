#!/usr/bin/env python
"""
set_up_group_trigger.py

An example program that can connect to a Dastard server as a short-lived client
to set up group triggering.

Suggested use: make a copy of this file and edit the variables just below this doc
string to suit your needs.
"""

from dastardcommander import rpc_client

# ----- <configuration> -----
# Configure the script by changing these variables.
Dastard_host = "localhost"
Dastard_port = "5500"
Connections = {
    # In this example, triggers on channel 1 cause secondary triggers on 3, 4, or 5,
    # and triggers on channel 2 cause secondaries on 5, 10, 15, or 20.
    1: [3, 4, 5],
    2: [5, 10, 15, 20]
}
Add_connections = True
Complete_disconnect = False
# ----- </configuration> -----


def main():
    client = rpc_client.JSONClient((Dastard_host, Dastard_port))
    try:
        if Complete_disconnect:
            dummy = True
            client.call("SourceControl.StopTriggerCoupling", dummy)
            print("Successfully disconnected all group trigger couplings")
            return

        state = {"Connections": Connections}
        request = "SourceControl.AddGroupTriggerCoupling"
        action = "added"
        if not Add_connections:
            request = "SourceControl.DeleteGroupTriggerCoupling"
            action = "deleted"
        client.call(request, state)
        print("Successfully {} group trigger couplings {}".format(action, Connections))

    finally:
        client.close()


if __name__ == "__main__":
    main()
