#!/bin/bash
cd log_viewer || exit
chmod +x autogen.sh
chmod +x log_viewer.py
./autogen.sh --prefix=$HOME/.local --libexecdir=$PWD
make install