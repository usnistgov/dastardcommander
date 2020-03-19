# Dastard Commander
GUI for operating [DASTARD](https://github.com/usnistgov/dastard), the Data Acquisition System for Triggering And Recording Data, a microcalorimeter DAQ system. dastard_commander is a GUI front-end only, and it communicates with a running Dastard system via JSON-RPC calls, as well as by monitoring certain ports for ZMQ messages.

## Installation
```
pip install -e git+https://github.com/usnistgov/dastard-commander#egg=dastard_commander
```

Requires Python 3 with Qt5. It is suggeste you use virtualenv and upgrade pip before installing. (See earlier versions of dastard_commander for Python 2).



## Running
From anywhere you should be able to run with `dcom` or `python -m dastard_commander`.


or equivalently, `./dc.py` should work, too. dastard_commander will then need to connect to a running Dastard. Give its host name (or IP) and port number. (Defaults are localhost:5000).

