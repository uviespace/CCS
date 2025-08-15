#!/usr/bin/env python3

"""
Remove PUS packet duplicates from binary file
"""

import sys
from smile_L0b_converter import remove_duplicates

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: ./remove_duplicates.py <INFILE> [<OUTFILE>]')
        sys.exit()
    elif len(sys.argv) == 2:
        infile = sys.argv[1]
        outfile = None
    else:
        infile, outfile = sys.argv[1:3]

    remove_duplicates(infile, outfile)