#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages
import os

setup(
    author="GCO, JF",
    author_email='galen.oneil@nist.gov',
    python_requires='>=3.5',
    description="Gui for DASTARD.",
    install_requires=["numpy", "PyQt5", "h5py", "zmq", "matplotlib"],
    license="MIT license",
    include_package_data=True,
    keywords='dastard_commander',
    name='dastard_commander',
    packages=["dastard_commander"],
    test_suite='tests',
    url='https://github.com/usnistgov/dastard_commander',
    version='0.1.0',
    zip_safe=False,
    package_data={'dastard_commander': ['ui/*.ui','ui/*.png']},
    entry_points = {
        'console_scripts': ['dc=dastard_commander.dc:main',
        "dc2=dastard_commander.dc:main2"],
    },
    scripts = ["dastard_commander/dc.py"],
)
