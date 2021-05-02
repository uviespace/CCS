#!/bin/bash
cd tst || exit
chmod +x autogen.sh
chmod +x tst.py
./autogen.sh --prefix=$HOME/.local --libexecdir=$PWD
make install