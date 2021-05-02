clone the project GIT repository
================================
git clone ssh://smile@herschel.astro.univie.ac.at:1722/home/smile/OBSW.git


install the GNU Make and Python package management system PIP
=============================================================
sudo apt install make
sudo apt install python3-pip


install sphinx for python3 + rtd theme for building documentation
=================================================================
sudo apt install python3-sphinx
pip3 install -U sphinx
pip3 install -U sphinx_rtd_theme


install the 'confignator' python package
========================================
Execute the Make-file in the implementation folder. Open the terminal change to the implementation folder and execute 'make install-confignator'


change the name and email of the git user
=========================================
git config --global --edit
git commit --amend --reset-author


Python modules
==============
pip3 install -U psutil
pip3 install -U bitstring
pip3 install -U sqlalchemy
pip3 install -U numpy
pip3 install -U crcmod
pip3 install -U astropy
pip3 install -U matplotlib
pip3 install -U rlipython  # nur für altes CHEOPS Projekt
pip3 install -U pydbus
pip3 install -U wheel


install MySql server
====================
sudo apt install mysql-server
sudo mysql_secure_installation utility

login into the MySQL shell as root and create an user and a database:
sudo mysql -u root -p
CREATE USER 'smile'@'localhost' IDENTIFIED BY 'letssmile';
CREATE DATABASE smiledb;
GRANT ALL PRIVILEGES ON smiledb . * TO 'smile'@'localhost';
FLUSH PRIVILEGES;

change the password policy (if necessary)
SET GLOBAL validate_password_policy=LOW;

install MySQL Python modules
============================
sudo apt install python-mysqldb
sudo apt install default-libmysqlclient-dev


# pip3 install mysql
# pip3 install mysql-python
# pip3 install mysqlclient



to compile the C code of CrIa, FwProfile, CrObc 
===============================================
apt install gcc-multilib


to inspect DBus services on the system
======================================
apt install d-feet


to browse the Gtk3 icons
========================
sudo apt install gtk-3-examples
# sudo apt install gtk3-icon-browser

In order to open the icon browser, open a terminal and execute the command 'gtk3-icon-browser'.


for the GTK Inspector
=====================
https://wiki.gnome.org/action/show/Projects/GTK/Inspector?action=show&redirect=Projects%2FGTK%2B%2FInspector
apt install libgtk-3-dev


additional git features
=======================
apt install gitk


Für das kompilieren des Simulators (CrIa) wird folgendes noch benötigt:
=======================================================================
apt install apt install libdbus-1-dev


install PyCharm
===============
download the .tar.gz
unpack where you want it
follow the instructions with the linux setup file (add to the PATH)

for a Application Launcher: open Pycharm (terminal pycharm.sh) -> Tools -> Create Desktop Entry

set the PYTHONPATH environment variable and add the PyCharm bin directory to PATH
=================================================================================
for Ubuntu 18.04.2 LTS (bionic) changes in the ~/.profile

::

    # ~/.profile: executed by the command interpreter for login shells.
    # This file is not read by bash(1), if ~/.bash_profile or ~/.bash_login
    # exists.
    # see /usr/share/doc/bash/examples/startup-files for examples.

    # the files are located in the bash-doc package.

    # the default umask is set in /etc/profile; for setting the umask
    # for ssh logins, install and configure the libpam-umask package.
    #umask 022

    # if running bash
    if [ -n "$BASH_VERSION" ]; then
        # include .bashrc if it exists
        if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
        fi
    fi

    # set PATH so it includes user's private bin if it exists
    if [ -d "$HOME/bin" ] ; then
        PATH="$HOME/bin:$PATH"
    fi

    # set PATH so it includes user's private bin if it exists
    if [ -d "$HOME/.local/bin" ] ; then
        PATH="$HOME/.local/bin:$PATH"
    fi

    # add PyCharm directory
    if [ -d "$HOME/.local/bin" ] ; then
        PATH="$HOME/pycharm/bin:$PATH"
    fi

    # ------------------------------ PYTHONPATH -------------------------------------

    # add CHEOPS CCS directory
    # PYTHONPATH="$HOME/cheops/Ccs/esa:$PYTHONPATH"

    # add SMILE CCS directory
    PYTHONPATH="$HOME/smile/implementation/Ccs/devel:$PYTHONPATH"

    # add SMILE TST directory
    PYTHONPATH="$HOME/smile/implementation/Tst:$PYTHONPATH"
    PYTHONPATH="$HOME/smile/implementation/Tst/tst:$PYTHONPATH"
    PYTHONPATH="$HOME/smile/implementation/Tst/progress_view:$PYTHONPATH"
    PYTHONPATH="$HOME/smile/implementation/Tst/sketch_desk:$PYTHONPATH"
    PYTHONPATH="$HOME/smile/implementation/Tst/test_specs:$PYTHONPATH"
    PYTHONPATH="$HOME/smile/implementation/Tst/tst/generator:$PYTHONPATH"
    export PYTHONPATH