#!/usr/bin/env python3
"""
Simulators - start/stop them
============================
"""

# TODO: many project specific methods -- implement more general functions, if necessary

import logging
import os
import subprocess
import psutil
import confignator


import logging
import logging.config
import logging.handlers

logging_format = '%(levelname)s\t%(asctime)s\t\t%(processName)s\t\t%(name)s\t\t%(message)s'


def set_level(logger):
    assert isinstance(logger, logging.Logger)
    # lvl = confignator.get_option(section='tst-logging', option='level')
    logger.setLevel(level=logging.DEBUG)


def create_console_handler(logger, frmt=logging_format):
    assert isinstance(logger, logging.Logger)
    hdlr = logging.StreamHandler()
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(logging.WARNING)
    logger.addHandler(hdlr=hdlr)


def create_file_handler(logger, frmt=logging_format):
    assert isinstance(logger, logging.Logger)
    file_name = confignator.get_option('paths', 'start-simulator-log')
    os.makedirs(os.path.dirname(file_name), mode=0o777, exist_ok=True)
    hdlr = logging.handlers.RotatingFileHandler(filename=file_name, mode='a', maxBytes=524288, backupCount=3)
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    logger.addHandler(hdlr=hdlr)

# create a logger
logger = logging.getLogger(__name__)
set_level(logger=logger)
create_console_handler(logger=logger)
create_file_handler(logger=logger)

# return a list of processes matching 'name'
def find_process_by_name(name):
    assert type(name) is str, name
    found_processes = []
    for process in psutil.process_iter():
        p_name, exe, cmdline = "", "", []
        try:
            p_name = process.name()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except psutil.NoSuchProcess:
            continue
        if name == p_name:
            found_processes.append(name)
    return found_processes


def obc_runs():
    """
    Check if the Onboard Computer simulator process is running, by searching after a process named 'CrObc'
    :return: bool
        True if a process called 'CrObc' is found
    """
    runs = False
    processes = find_process_by_name('CrObc')
    if len(processes) > 0:
        runs = True
    return runs


def ia_runs():
    """
    Check if the IA simulator process is running, by searching after a process named 'CrIa'
    :return: bool
        True if a process called 'CrIa' is found
    """
    runs = False
    processes = find_process_by_name('CrIa')
    if len(processes) > 0:
        runs = True
    return runs


def sem_runs():
    """
    Check if the SEM simulator process is running, by searching after a process named 'CrSem'
    :return: bool
        True if a process called 'CrSem' is found
    """
    runs = False
    processes = find_process_by_name('CrSem')
    if len(processes) > 0:
        runs = True
    return runs

def start_crplm():
    logger.info('Starting CrPlm simulator process')
    path = confignator.get_option('paths', 'crplm')
    path = os.path.realpath(path)
    logger.debug('starting CrPlm: path to executable: {}'.format(path))
    cmd1 = 'gnome-terminal --geometry 63x21+0+5 --title="CrPlm" --working-directory="' + path + '" -e "./CrPlm"'
    crplm = subprocess.Popen("exec " + cmd1, stdin=None, stdout=None, stderr=None, shell=True)
    return crplm

def start_obc():
    start_crplm()

def start_ia():
    logger.info('Starting CrIa simulator process')
    path = confignator.get_option('paths', 'ia')
    logger.debug('starting DPU: path to executable: {}'.format(path))
    path = os.path.realpath(path)
    cmd2 = 'gnome-terminal --geometry 63x21+0+375 --title="CrIa" --working-directory="' + path + '" -e "./CrIa"'
    cria = subprocess.Popen("exec " + cmd2, stdin=None, stdout=None, stderr=None, shell=True)
    return cria


def start_datasim():
    logger.info('Starting data simulator process starsim')
    path = confignator.get_option('paths', 'datasim')
    logger.debug('starting DataSim: path to executable: {}'.format(path))
    path = os.path.realpath(path)
    cmd3 = 'gnome-terminal --geometry 80x30+580+495 --title="DataSim" --working-directory="' + path + \
           '" -H -e "python socket_server_starsim.py"'
    datasim = subprocess.Popen("exec " + cmd3, stdin=None, stdout=None, stderr=None, shell=True)
    return datasim


def start_sem():
    logger.info('Starting SEM simulator process')
    path = confignator.get_option('paths', 'sem')
    logger.debug('starting SEM: path to executable: {}'.format(path))
    path = os.path.realpath(path)
    cmd4 = 'gnome-terminal --geometry 80x30+0+495 --title="CrSem" --working-directory="' + path + '" -e "./CrSem"'
    crsem = subprocess.Popen("exec " + cmd4, stdin=None, stdout=None, stderr=None, shell=True)
    return crsem


def start_sem_w_fits():
    """
    Starts the SEM simulator as a subprocess.
    If the SEM simulator is already running, no further process is started.
    
    :return: subprocess.Popen || None
        Popen object of the SEM simulator process or None if it is already running.
    """
    crsem = None

    # check if the CrSem process is already running
    is_sem_running = sem_runs()
    if is_sem_running is False:
        # switch on the SEM simulator
        logger.info('Starting SEM simulator process using FIT files')
        path = confignator.get_option('paths', 'sem')
        path = os.path.realpath(path)
        cmd = 'gnome-terminal --geometry 80x21+0+725 --title="CrSem" --working-directory="' + path + \
              '" -e "./CrSem -f ~/IFSW/acceptance_tests/fits/FF.fits -w ~/IFSW/acceptance_tests/fits/WIN.fits"'
        # gdb -ex=r --args
        crsem = subprocess.Popen("exec " + cmd, stdin=None, stdout=None, stderr=None, shell=True)
    else:
        logger.info('CrSem is already running')

    return crsem


def start_sem_w_datasim():
    logger.info('Starting SEM simulator process with data simulator')
    path = confignator.get_option('paths', 'sem')
    path = os.path.realpath(path)
    cmd4 = 'gnome-terminal --geometry 80x30+0+495 --title="CrSem" --working-directory="' + path + '" -e "./CrSem"'
    crsem = subprocess.Popen("exec " + cmd4, stdin=None, stdout=None, stderr=None, shell=True)
    datasim = start_datasim()
    return crsem, datasim


def stop_obc(obc):
    """
    Stopping the Onboard Computer simulator process.
    If the subprocess is known, it is terminated.
    If no subprocess is known, a process with the name 'CrObc' is searched and if found, killed.
    :param obc: subprocess.popen
        instance of subprocess.popen
    """
    logger.info('Stopping CrObc simulator process')
    if obc is not None:
        obc.terminate()
    else:
        # find the process with the name CrObc and kill it
        processes = find_process_by_name('CrObc')
        if len(processes) > 0:
            os.system('killall CrObc')


def stop_ia(ia):
    """
    Stopping the IA simulator process.
    If the subprocess is known, it is terminated.
    If no subprocess is known, a process with the name 'CrIa' is searched and if found, killed.
    :param ia: subprocess.popen
        instance of subprocess.popen
    """
    logger.info('Stopping CrIa simulator process')
    if ia is not None:
        ia.terminate()
    else:
        # find the process with the name CrIa and kill it
        processes = find_process_by_name('CrIa')
        if len(processes) > 0:
            os.system('killall CrIa')


def stop_sem(sem):
    """
    Stopping the SEM simulator process.
    If the subprocess is known, it is terminated.
    If no subprocess is known, a process with the name 'CrSem' is searched and if found, killed.
    :param sem: subprocess.popen
        instance of subprocess.popen
    """
    logger.info('Stopping CrSem simulator process')
    if sem is not None:
        sem.terminate()
    else:
        # find the process with the name CrSem and kill it
        processes = find_process_by_name('CrSem')
        if len(processes) > 0:
            os.system('killall CrSem')


def stop_datasim(datasim):
    logger.info('Stopping starsim data simulator process')
    if datasim is not None:
        datasim.terminate()
