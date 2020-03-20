# Dastard Commander
Dastard Commander is a GUI for operating [DASTARD](https://github.com/usnistgov/dastard) (the Data Acquisition System for Triggering And Recording Data), a microcalorimeter DAQ system. Dastard Commander is a GUI front-end only, and it communicates with a running Dastard system via JSON-RPC calls, as well as by monitoring certain ports for ZMQ messages.

## Installation

### Pip
It is suggested you use virtualenv and upgrade pip before installing.

Joe doesn't understand the former. You can do the latter with:
```
pip install --upgrade pip
```

### Installation of Dastard Commander
```
pip install -e git+https://github.com/usnistgov/dastardcommander#egg=dastardcommander
```

Requires Python 3 with Qt5.  The `-e` or `--editable` argument is not _required_ for installation, but it will make debugging and development easier: it makes a git repository clone in `src/dastardcommander` relative to your current working directory. If you are a 100% user with no aspirations to develop, then omit the `-e`.

If you need a specific branch, the syntax is `pip install -e git+https://github.com/usnistgov/dastardcommander@branch#egg=dastardcommander`.

Keep an eye out for the WARNING you might see if the installation directory is not in your PATH. If that happens, you should add to your path the directory it points out by editing your `~/.bash_profile` or `~/.bashrc` as needed (and remember that editing the file does not take immediate effect). On a Mac OS X, that installation directory was `~/Library/Python/3.8/bin`. Other OS would probably have a different location.


## Running Dastard Commander
From anywhere you should be able to run with `dcom` or `python -m dastardcommander`. Dastard Commander will then need to connect to a running instance of Dastard. Give its host name (or IP) and port number. (Defaults are `localhost:5000`). Although remote operation is possible, beware that firewall rules on either computer might be blocking the necessary traffic on ports 5000-5004.

If you have installed with the editable option, then this command will load your local and _potentially edited_ version of the package. That's probably what you want.
