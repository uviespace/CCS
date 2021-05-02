#!/usr/bin/env python3
import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

with open('LICENSE') as f:
    license_text = f.read()

setuptools.setup(
    name='testlib',
    version='1.0.0',
    author='Stefan Winkler',
    author_email='stefan_winkler@univie.ac.at',
    description='For testing SMILE IASW. Functions for test scripts to analyse the TC/TM pool and writing a log file. ',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='',
    license=license_text,
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License',
        'Operating System',
    ],
)
