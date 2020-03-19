# Dastard Commander
GUI for operating [DASTARD](https://github.com/usnistgov/dastard), the Data Acquisition System for Triggering And Recording Data, a microcalorimeter DAQ system. dastard_commander is a GUI front-end only, and it communicates with a running Dastard system via JSON-RPC calls, as well as by monitoring certain ports for ZMQ messages.

## Installation
```
pip install -e git+https://github.com/usnistgov/dastardcommander#egg=dastardcommander
```

Requires Python 3 with Qt5. It is suggeste you use virtualenv and upgrade pip before installing. The `-e` argument is not required for installation, but it will make debugging and development easier. If you need a specific branch use `pip install -e git+https://github.com/usnistgov/dastardcommander@branch#egg=dastardcommander`. 



## Running
From anywhere you should be able to run with `dcom` or `python -m dastardcommander`. dastard_commander will then need to connect to a running Dastard. Give its host name (or IP) and port number. (Defaults are localhost:5000).

