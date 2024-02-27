# Dastard Commander
Dastard Commander is a GUI for operating [DASTARD](https://github.com/usnistgov/dastard) (the Data Acquisition System for Triggering And Recording Data), a microcalorimeter DAQ system. Dastard Commander is a GUI front-end only based on Qt5. It communicates with a running Dastard system via JSON-RPC calls, as well as by monitoring certain ports for ZMQ messages. It requires Python 3.8 or later versions (Python 3.7 and all earlier versions are past their [end-of-life-date](https://devguide.python.org/versions/)).

## Installation

### xcb
```
sudo apt install "libxcb*"
```
This is required for some sort of qt plugin, and we seem to have problems as of Ubuntu 20 if we don't do it.

### Pip in a virtualenv but without Conda (recommended)
This project requires Python 3. We suggest that you use virtualenv and also that you upgrade pip before installing. Suppose you want to put dastardcommander in a virtualenv located at `~/qsp/`. This setup would look like:
```
python3 -m venv ~/qsp
source ~/qsp/bin/activate
pip install --upgrade pip
pip install -e git+ssh://git@github.com/usnistgov/dastardcommander.git#egg=dastardcommander
```

The first line is safe (but optional) if you already have a virtualenv at `~/qsp/`. Thanks to [nist-qsp-tdm](https://bitbucket.org/nist_microcal/nist-qsp-tdm/src/master/) for these instructions.

The `-e` or `--editable` argument is not _required_ for installation, but it will make debugging and development easier: it makes a git repository clone in `src/dastardcommander` relative to your virtualenv. If you are a 100% user with no aspirations to develop, then omit the `-e` and you'll find the clone several directories deep under `lib` in the virtualenv. (Or more likely, you won't find it, but it's there nevertheless.)

If you need a specific branch, the syntax is
```
pip install -e git+https://github.com/usnistgov/dastardcommander@SPECIFIC_BRANCH#egg=dastardcommander
```
Obviously, replace `SPECIFIC_BRANCH` with the actual name of the desired branch.

### Conda + pip (also recommended)

If you want Anaconda python to be in charge of your environment(s), you create and activate your environment similar to the above, but slightly different. Steps 1+2 (create+activate) would look like this, assuming `qsp` is still the name chosen for your environment:
```
conda create -n qsp
conda activate qsp
pip install --upgrade pip
pip install -e git+ssh://git@github.com/usnistgov/dastardcommander.git#egg=dastardcommander
```
As conda will probably tell you, the environment from this example would live in `~/installs/anaconda3/envs/qsp`. See above for the editable argument and choosing a specific branch.

### No virtualenv (not recommended)
I (Joe) used to install without a virtualenv. It required only a small one-time effort to make sure `PATH` and `PYTHONPATH` were correct, and it worked great...until it didn't. So as of Feb 2022, I switched to using a virtualenv. You should, too. But if you don't feel like it, you can try to install outside of one:

```
pip install --upgrade pip
pip install -e git+https://github.com/usnistgov/dastardcommander#egg=dastardcommander
```

The `-e` or `--editable` argument is not _required_ for installation, but it will make debugging and development easier: it makes a git repository clone in `src/dastardcommander` relative to your current working directory. If you are a 100% user with no aspirations to develop, then omit the `-e`. On the other hand, if you need a specific branch, use the `@SPECIFIC_BRANCH` command given in the previous section.

Keep an eye out for the WARNING you might see if the installation directory is not in your PATH. If that happens, you should add to your path the directory it points out by editing your `~/.bash_profile` or `~/.bashrc` as needed (and remember that editing the file does not take immediate effect). On a Mac OS X, that installation directory was `~/Library/Python/3.9/bin`. Other OS would use a different location.

## Running Dastard Commander
If you installed in a virtualenv, then you'll need to activate it in the terminal that you'll use, probably with one of:
```
# Virtualenv, non-Conda users:
source ~/qsp/bin/activate

# Conda users:
conda activate qsp
```
You can do this within the `~/.bashrc` configuration file if you are sure you want this virtualenv active in each terminal you ever start.

Once the environment is activated, you should be able to run with `dcom` or the equivalent `python -m dastardcommander` from any directory. Dastard Commander will then need to connect to a running instance of Dastard. Give its host name (or IP) and port number. (Defaults are `localhost:5500`). Although remote operation is possible, beware that firewall rules on either computer might be blocking the necessary traffic on ports 5500-5504.

If you have installed with the editable option, then this command will load your local and _potentially edited_ version of the package. That's probably what you want.

### Examples

The directory `examples/` contains the script `set_up_group_trigger.py`. If you want to manipulate group triggering in some more complicated way than the GUI allows, or you want a permanent record of what you set up, this is for you. Copy that script to another directory and edit the block marked by `<configuration>` comments to make it do what you want. Then you can run it at the terminal (there's no need to stop Dastard Commander, if it's running).

Other example scripts may go here in the future.
