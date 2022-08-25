#!/usr/bin/env python3
"""
Opens the documentation of the confignator package in firefox.
"""
import os
import webbrowser
from confignator import config


def open_documentation_in_firefox():
    docu = config.get_option('confignator-paths', 'docu')

    if not os.path.isfile(docu):
        raise FileNotFoundError('Documentation not found: {}. Try rebuilding it.'.format(docu))

    webbrowser.open(docu)


if __name__ == '__main__':
    open_documentation_in_firefox()
