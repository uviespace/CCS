#!/usr/bin/env python3
import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

with open('LICENSE') as f:
    license_text = f.read()

setuptools.setup(
    name='confignator',
    version='2.0.0',
    author='Stefan Winkler',
    author_email='stefan_winkler@univie.ac.at',
    description='For editing and handling the access to the configuration files',
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
    package_data={
        '': ['*.*'],
    }
)
