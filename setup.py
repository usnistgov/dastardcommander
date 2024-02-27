#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

setup(
    author="GCO, JF",
    author_email="galen.oneil@nist.gov",
    python_requires=">=3.8",
    description="Gui for DASTARD.",
    install_requires=["numpy", "PyQt5", "h5py", "zmq", "matplotlib", "pyyaml"],
    license="MIT license",
    include_package_data=True,
    keywords="dastardcommander",
    name="dastardcommander",
    packages=["dastardcommander"],
    test_suite="tests",
    url="https://github.com/usnistgov/dastardcommander",
    version="0.2.8",
    zip_safe=False,
    package_data={"dastardcommander": ["ui/*.ui", "ui/*.png"]},
    entry_points={
        "console_scripts": ["dcom=dastardcommander.dc:main"],
    },
)
