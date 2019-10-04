# Dastard-Commander
GUI for operating [DASTARD](https://github.com/usnistgov/dastard), the Data Acquisition System for Triggering And Recording Data, a microcalorimeter DAQ system. Dastard-Commander is a GUI front-end only, and it communicates with a running Dastard system via JSON-RPC calls, as well as by monitoring certain ports for ZMQ messages.

## Installation
Requires Python2 with Qt5 (but Python3 conversion is coming soon, as of 4 October 2019).

The usual platform for microcalorimeter systems is Ubuntu 16 or 18. DC should work on Mac OS X or Windows, too, though Mac testing is limited and Windows has not been attempted.

For Ubuntu, installation should be as simple as:
```
sudo apt-get install python-pyqt5
cd  # Replace by cd to wherever you wish to store the repo, if not in your home directory.
git clone https://github.com/usnistgov/dastard-commander.git

sudo apt-get install roxterm  # add this if you want the scripting in roxterms.sh
```

## Running
From the top directory of this repository, just do
```
python dc.py
```

or equivalently, `./dc.py` should work, too. Dastard-Commander will then need to connect to a running Dastard. Give its host name (or IP) and port number. (Defaults are localhost:5000).

### Running multiple tabs for TDM operation within RoxTerm
The following is a quick way to get the necessary tabs and directories pre-configured.
```
cd ~/dastard-commander
roxterm
# from within roxterm:
bash roxterms.sh
# (close unused roxterm)

# in dastard tab:
go run cmd/dastard/dastard.go

# in dc tab:
python dc.py

# in cringe tab:
python cringe.py -L
```
