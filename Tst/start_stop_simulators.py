#!/usr/bin/env python3
"""
Functions for the starting and stopping Simulators
==================================================
The Simulators are started as subprocess using subprocess.Popen. The command which is used is *gnome-terminal*.
Stopping the simulators is done by searching for the name of the process and kill it.
Functions to check if a process is already running, are available.
"""
import os
import subprocess
import psutil
import logging

import confignator
import toolbox


process_name_crplm = 'CrPlm'
process_name_cria = 'CrIa'


log_file_path = confignator.get_option(section='logging', option='log-dir')
log_file = os.path.join(log_file_path, 'start_stop_simulators.log')

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)
file_hdlr = toolbox.create_file_handler(file=log_file)
logger.addHandler(hdlr=file_hdlr)


def build_command(file_name: str, working_dir: str) -> str:
    cmd = ''
    cmd += 'gnome-terminal'
    # cmd += ' --geometry 63x21+0+5'
    cmd += ' --title=' + file_name
    cmd += ' --working-directory="' + working_dir + '"'
    cmd += ' -- "./' + file_name + '"'
    return cmd


def find_process_by_name(name: str, logger: logging.Logger = logger) -> list:
    """
    Return a list of processes matching 'name'
    :param logging.Logger logger: the logger
    :param str name: name of the process
    :return: list of process names
    :rtype: list
    """
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
            logger.debug('Found a process with the name {}'.format(name))
            found_processes.append(name)
    return found_processes


def is_process_running(process_name: str, logger: logging.Logger = logger) -> bool:
    """
    Checks if there is a process with the name
    :param str process_name: Name of the process which should be found.
    :param logging.Logger logger: the logger
    :return: True if the process is found
    :rtype: bool
    """
    runs = False
    processes = find_process_by_name(name=process_name, logger=logger)
    if len(processes) > 0:
        runs = True
    return runs


def crplm_runs(logger: logging.Logger = logger) -> bool:
    """
    Check if the Onboard-Computer simulator process is running, by searching after the name of the process
    :param logging.Logger logger: the logger
    :return: True if a process called 'CrPlm' is found
    :rtype: bool
    """
    return is_process_running(process_name=process_name_crplm, logger=logger)


def cria_runs(logger: logging.Logger = logger) -> bool:
    """
    Check if the IA simulator process is running, by searching after the name of the process
    :param logging.Logger logger: the logger
    :return: True if a process called 'CrIa' is found
    :rtype: bool
    """
    return is_process_running(process_name=process_name_cria, logger=logger)


def start_crplm(logger: logging.Logger = logger) -> subprocess.Popen:
    """
    Start the CrPlm simulator process.
    :param logging.Logger logger: the logger
    :return: the subprocess of CrPlm
    :rtype: subprocess.Popen
    """
    logger.info('Starting CrPlm simulator process')
    path = confignator.get_option('paths', 'crplm')
    command = build_command(file_name=process_name_crplm, working_dir=path)
    logger.debug('command: {}'.format(command))
    crplm = subprocess.Popen("exec " + command, stdin=None, stdout=None, stderr=None, shell=True)
    return crplm


def start_cria(logger: logging.Logger = logger) -> subprocess.Popen:
    """
    Start the CrPlm simulator process.
    :param logging.Logger logger: the logger
    :return: the subprocess of CrIa
    :rtype: subprocess.Popen
    """
    logger.info('Starting CrIa simulator process')
    path = confignator.get_option('paths', 'ia')
    command = build_command(file_name=process_name_cria, working_dir=path)
    logger.debug('command: {}'.format(command))
    cria = subprocess.Popen("exec " + command, stdin=None, stdout=None, stderr=None, shell=True)
    return cria


def stop_crplm(logger: logging.Logger = logger):
    """
    Stopping the Onboard Computer simulator process.
    A process with the name of the process_name_crplm is searched and if found, killed.
    :param logging.Logger logger: the logger
    """
    logger.info('Stopping CrPlm simulator process')
    processes = find_process_by_name(name=process_name_crplm, logger=logger)
    if len(processes) > 0:
        command = 'killall ' + process_name_crplm
        logger.debug('Executing os.system command: {}'.format(command))
        os.system(command)


def stop_cria(logger: logging.Logger = logger):
    """
    Stopping the IA simulator process.
    A process with the name of the process_name_cria is searched and if found, killed.
    :param logging.Logger logger: the logger
    """
    logger.info('Stopping CrIa simulator process')
    processes = find_process_by_name(name=process_name_cria, logger=logger)
    if len(processes) > 0:
        command = 'killall ' + process_name_cria
        logger.debug('Executing os.system command: {}'.format(command))
        os.system(command)
