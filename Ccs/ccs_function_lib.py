"""
Utility functions for packet handling in CCS
"""

import gi
gi.require_version('Gtk', '3.0')
# gi.require_version('Notify', '0.7')

from gi.repository import Gtk, GLib, GdkPixbuf  #, Notify
import subprocess
import struct
import datetime
import dateutil.parser as duparser
import io
import types
import sys
import select
import json
import time
import dbus
import socket
import os
from pathlib import Path
import glob
import numpy as np
import logging.handlers
from database.tm_db import scoped_session_maker, DbTelemetry, DbTelemetryPool, RMapTelemetry, FEEDataTelemetry
from sqlalchemy.exc import OperationalError as SQLOperationalError
from sqlalchemy.sql.expression import func
import threading

from typing import NamedTuple
from s2k_partypes import ptt, ptt_reverse, ptype_parameters, ptype_values
import confignator
import importlib

import timeformats

cfg = confignator.get_config(check_interpolation=False)

PCPREFIX = 'packet_config_'
CFG_SECT_PLOT_PARAMETERS = 'ccs-plot_parameters'
CFG_SECT_DECODE_PARAMETERS = 'ccs-decode_parameters'

# Set up logger
CFL_LOGGER_NAME = 'cfl'
logger = logging.getLogger(CFL_LOGGER_NAME)
logger.setLevel(getattr(logging, cfg.get('ccs-logging', 'level').upper()))
# sh = logging.StreamHandler()
# sh.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
# logger.addHandler(sh)

communication = {name: 0 for name in cfg['ccs-dbus_names']}

scoped_session_idb = scoped_session_maker('idb', idb_version=None)
scoped_session_storage = scoped_session_maker('storage')

# check if MIB schema exists
try:
    scoped_session_idb.execute('show schemas').fetchall()
except SQLOperationalError as err:
    logger.critical(err)
    sys.exit()

# MIB caches to reduce SQL load
_pcf_cache = {}
_cap_cache = {}
_txp_cache = {}
_pcf_descr_cache = {}

project = cfg.get('ccs-database', 'project')
pc = importlib.import_module(PCPREFIX + str(project).upper())

# project specific parameters, must be present in all packet_config_* files
try:
    PUS_VERSION, TMHeader, TCHeader, PHeader, TM_HEADER_LEN, TC_HEADER_LEN, P_HEADER_LEN, PEC_LEN, MAX_PKT_LEN, timepack, \
        timecal, calc_timestamp, CUC_OFFSET, CUC_EPOCH, crc, PLM_PKT_PREFIX_TC_SEND, PLM_PKT_SUFFIX, FMT_TYPE_PARAM = \
        [pc.PUS_VERSION, pc.TMHeader, pc.TCHeader, pc.PHeader,
         pc.TM_HEADER_LEN, pc.TC_HEADER_LEN, pc.P_HEADER_LEN, pc.PEC_LEN,
         pc.MAX_PKT_LEN, pc.timepack, pc.timecal, pc.calc_timestamp,
         pc.CUC_OFFSET, pc.CUC_EPOCH, pc.puscrc, pc.PLM_PKT_PREFIX_TC_SEND, pc.PLM_PKT_SUFFIX, pc.FMT_TYPE_PARAM]

    s13_unpack_data_header = pc.s13_unpack_data_header
    SPW_PROTOCOL_IDS_R = {pc.SPW_PROTOCOL_IDS[key]: key for key in pc.SPW_PROTOCOL_IDS}

    tmtc = pc.TMTC
    tsync_flag = pc.TSYNC_FLAG

except AttributeError as err:
    logger.critical(err)
    raise err

try:
    cal = importlib.import_module('calibrations_' + str(project).upper())
except Exception as err:
    logger.warning(err)
    cal = None

SREC_MAX_BYTES_PER_LINE = 250
SEG_HEADER_FMT = '>III'
SEG_HEADER_LEN = struct.calcsize(SEG_HEADER_FMT)
SEG_SPARE_LEN = 2
SEG_CRC_LEN = 2

pid_offset = int(cfg.get('ccs-misc', 'pid_offset'))

fmtlist = {'INT8': 'b', 'UINT8': 'B', 'INT16': 'h', 'UINT16': 'H', 'INT32': 'i', 'UINT32': 'I', 'INT64': 'q',
           'UINT64': 'Q', 'FLOAT': 'f', 'DOUBLE': 'd', 'INT24': 'i24', 'UINT24': 'I24', 'uint*': 'uint',
           'ascii*': 'ascii', 'oct*': 'oct'}

personal_fmtlist = []

fmtlengthlist = {'b': 1, 'B': 1, 'h': 2, 'H': 2, 'i': 4, 'I': 4, 'q': 8,
                 'Q': 8, 'f': 4, 'd': 8, 'i24': 3, 'I24': 3}

# get format and offset of SIDs/discriminants
SID_FORMAT = {8: '>B', 16: '>H', 32: '>I'}
try:
    _sidfmt = scoped_session_idb.execute('SELECT PIC_TYPE,PIC_STYPE,PIC_APID,PIC_PI1_OFF,PIC_PI1_WID FROM pic').fetchall()
    if len(_sidfmt) != 0:
        SID_LUT = {tuple(k[:3]): tuple(k[3:]) for k in _sidfmt}
    else:
        SID_LUT = {}
        logger.warning('SID definitions not found in MIB!')
except SQLOperationalError:
    _sidfmt = scoped_session_idb.execute('SELECT PIC_TYPE,PIC_STYPE,PIC_PI1_OFF,PIC_PI1_WID FROM pic').fetchall()
    SID_LUT = {tuple([*k[:2], None]): tuple(k[2:]) for k in _sidfmt}
    logger.warning('MIB structure not fully compatible, no APID in PIC for SID format definition.')


# get names of TC parameters that carry data pool IDs, i.e. have CPC_CATEG=P
DATA_POOL_ID_PARAMETERS = [par[0] for par in scoped_session_idb.execute('SELECT cpc_pname FROM cpc WHERE cpc_categ="P"').fetchall()]


counters = {}  # keeps track of PUS TC packet sequence counters (one per APID)

if cfg.has_section('ccs-user_defined_packets'):
    user_tm_decoders = {k: json.loads(cfg['ccs-user_defined_packets'][k]) for k in cfg['ccs-user_defined_packets']}
else:
    user_tm_decoders = {}


ActivePoolInfo = NamedTuple(
    'ActivePoolInfo', [
        ('filename', str),
        ('modification_time', int),
        ('pool_name', str),
        ('live', bool)])


def _reset_mib_caches():
    _pcf_cache.clear()
    _cap_cache.clear()
    _txp_cache.clear()


def _add_log_socket_handler():
    global logger
    # check if a handler is already present
    for hdlr in logger.handlers:
        if isinstance(hdlr, logging.handlers.SocketHandler):
            return
    sh = logging.handlers.SocketHandler('localhost', logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    sh.setFormatter(logging.Formatter('%(asctime)s: %(name)-15s %(levelname)-8s %(message)s'))
    logger.addHandler(sh)


def _remove_log_socket_handlers():
    global logger
    for hdlr in logger.handlers:
        if isinstance(hdlr, logging.handlers.SocketHandler):
            logger.removeHandler(hdlr)


def set_scoped_session_idb_version(idb_version=None):
    """

    :param idb_version:
    """
    global scoped_session_idb
    scoped_session_idb.close()
    scoped_session_idb = scoped_session_maker('idb', idb_version=idb_version)

    _reset_mib_caches()

    logger.info('MIB SQL reconnect ({})'.format(idb_version))


def get_scoped_session_storage():
    """

    :return:
    """
    return scoped_session_maker('storage')


def start_app(file_path, wd, *args, console=False, **kwargs):
    """
    
    :param file_path:
    :param wd:
    :param args:
    :param console:
    :param kwargs:
    """
    # gui argument only used for poolmanager since it does not have an automatic gui
    if not os.path.isfile(file_path):
        raise FileNotFoundError('File not found: {}'.format(file_path))

    if kwargs:
        logger.info('{}: some parameters are not handled: {}'.format(file_path, kwargs))

    if not console:
        command = ''
        command += 'nohup python3 '
        command += file_path
        for arg in args:
            command += ' '
            command += arg
        command += ' >/dev/null 2>&1 &'
        logger.debug('Command to be executed: {}'.format(command))
        os.system(command)
    else:
        subprocess.Popen(['python3', file_path, *args], cwd=wd)


# Start the poolviewer
def start_pv(pool_name=None, console=False, **kwargs):
    """
    Gets the path of the Startfile for the Poolviewer and executes it
    
    :param console: If False will be run in Console, otherwise will be run in separate Environment
    :return:
    """

    directory = cfg.get('paths', 'ccs')
    file_path = os.path.join(directory, 'poolview_sql.py')
    if pool_name is not None:
        start_app(file_path, directory, pool_name, console=console, **kwargs)
    else:
        start_app(file_path, directory, console=console, **kwargs)


# Start only PoolManager
def start_pmgr(gui=True, console=False, **kwargs):
    """
    Gets the path of the Startfile for the Poolmanager and executes it
    
    :param console: If False will be run in Console, otherwise will be run in separate Environment
    :return:
    """

    directory = cfg.get('paths', 'ccs')
    file_path = os.path.join(directory, 'pus_datapool.py')

    if not gui:
        start_app(file_path, directory, '--nogui', console=console, **kwargs)
    else:
        start_app(file_path, directory, console=console, **kwargs)


# Start Editor
# Argumnet gives the possibility to run file in the console to see print comands
def start_editor(*files, console=False, **kwargs):
    """
    Gets the path of the Startfile for the Editor and executes it
    
    :param console: If False will be run in Console, otherwise will be run in separate Environment
    :return:
    """

    directory = cfg.get('paths', 'ccs')
    file_path = os.path.join(directory, 'editor.py')

    start_app(file_path, directory, *files, console=console, **kwargs)


# Start Parameter Monitor
# Argumnet gives the possibility to run file in the console to see print comands
def start_monitor(pool_name, parameter_set=None, console=False, **kwargs):
    """
    Gets the path of the Startfile for the Monitor and executes it
    
    :param console: If False will be run in Console, otherwise will be run in separate Environment
    :return:
    """

    directory = cfg.get('paths', 'ccs')
    file_path = os.path.join(directory, 'monitor.py')

    if parameter_set is not None:
        start_app(file_path, directory, pool_name, parameter_set, console=console, **kwargs)
    else:
        start_app(file_path, directory, pool_name, console=console, **kwargs)


# Start Parameter Plotter
# Argumnet gives the possibility to run file in the console to see print comands
def start_plotter(pool_name, console=False, **kwargs):
    """
    Gets the path of the Startfile for the Plotter and executes it
    
    :param pool_name:
    :param console: If False will be run in Console, otherwise will be run in separate Environment
    :return:
    """
    directory = cfg.get('paths', 'ccs')
    file_path = os.path.join(directory, 'plotter.py')

    start_app(file_path, directory, pool_name, console=console, **kwargs)


def start_tst(console=False, **kwargs):
    """

    :param console:
    :param kwargs:
    """
    directory = cfg.get('paths', 'tst')
    file_path = os.path.join(directory, 'tst/main.py')
    start_app(file_path, directory, console=console, **kwargs)


def start_progress_view(console=False, **kwargs):
    """

    :param console:
    :param kwargs:
    """
    directory = cfg.get('paths', 'tst')
    file_path = os.path.join(directory, 'progress_view/progress_view.py')
    start_app(file_path, directory, console=console, **kwargs)


def start_log_viewer(console=False, **kwargs):
    """

    :param console:
    :param kwargs:
    """
    directory = cfg.get('paths', 'tst')
    file_path = os.path.join(directory, 'log_viewer/log_viewer.py')
    start_app(file_path, directory, console=console, **kwargs)


def start_config_editor(console=False, **kwargs):
    """

    :param console:
    :param kwargs:
    """
    file_path = cfg.get('start-module', 'config-editor')
    directory = os.path.dirname(file_path)
    start_app(file_path, directory, console=console, **kwargs)


def start_tst(console=False, **kwargs):
    """

    :param console:
    :param kwargs:
    """
    file_path = os.path.join(cfg.get('paths', 'base'), 'start_tst')
    directory = os.path.dirname(file_path)
    start_app(file_path, directory, console=console, **kwargs)


# This sets up a logging client for the already running TCP-logging Server,
# The logger is returned with the given name an can be used like a normal logger
def start_logging(name):
    """

    :param name:
    :return:
    """
    level = cfg.get('ccs-logging', 'level')
    loglevel = getattr(logging, level.upper())

    rootLogger = logging.getLogger('')
    rootLogger.setLevel(loglevel)
    socketHandler = logging.handlers.SocketHandler('localhost', logging.handlers.DEFAULT_TCP_LOGGING_PORT)

    # don't bother with a formatter, since a socket handler sends the event as an unformatted pickle
    rootLogger.addHandler(socketHandler)
    log = logging.getLogger(name)

    return log


# This returns a dbus connection to a given Application-Name
def dbus_connection(name, instance=1):
    """

    :param name:
    :param instance:
    :return:
    """
    if instance == 0:
        logger.warning('No instance of {} found.'.format(name))
        return False

    if not instance:
        instance = 1

    dbus_type = dbus.SessionBus()
    try:
        Bus_Name = cfg.get('ccs-dbus_names', name)
    except (ValueError, confignator.config.configparser.NoOptionError):
        logger.warning(str(name) + ' is not a valid DBUS name.')
        logger.warning(str(name) + ' not found in config file.')
        raise NameError('"{}" is not a valid module name'.format(name))

    Bus_Name += str(instance)

    try:
        dbuscon = dbus_type.get_object(Bus_Name, '/MessageListener')
        return dbuscon
    except:
        # print('Please start ' + str(name) + ' if it is not running')
        logger.warning('Connection to ' + str(name) + ' is not possible.')
        return False


# Returns True if application is running or False if not
def is_open(name, instance=1):
    """

    :param name:
    :param instance:
    :return:
    """
    dbus_type = dbus.SessionBus()
    try:
        # dbus_connection(name, instance)
        Bus_Name = cfg.get('ccs-dbus_names', name)
        Bus_Name += str(instance)
        dbus_type.get_object(Bus_Name, '/MessageListener')
        return True
    except Exception as err:
        logger.debug(err)
        return False


def show_functions(conn, filter=None):
    """
    Show all available functions for a CCS application
    
    :param conn: A Dbus connection
    :param filter: A string which filters the results
    :return: A list of available functions
    """
    '''
    if app_nbr and not isinstance(app_nbr, int):
        filter = app_nbr
        conn = dbus_connection(app_name)
    else:
        conn = dbus_connection(app_name, app_nbr)
    '''

    if filter:
        method_list = conn.show_functions(filter)
    else:
        method_list = conn.show_functions()

    method_list2 = []
    for i in method_list:
        method_list2.append(str(i))

    return method_list2


def ConnectionCheck(dbus_con, argument=None):
    """
    The user friendly version to use the ConnectionCheck method exported by all CCS applications via DBus, checks if the
    connection is made
    
    :param dbus_con: A Dbus connection
    :param argument: An argument which can be sent for testing purposes
    :return: If the connection is made
    """
    argument = python_to_dbus(argument, True)

    if argument:
        result = dbus_con.ConnectionCheck(argument)
    else:
        result = dbus_con.ConnectionCheck()

    result = dbus_to_python(result, True)

    return result


def Functions(dbus_con, function_name, *args, **kwargs):
    """
    The user friendly version to use the Functions method exported by all CCS applications via DBus, lets one call all
    Functions in a CCS application

    :param dbus_con: A Dbus connection
    :param function_name: The function to call as a string
    :param args: The arguments for the function
    :param kwargs: The keyword arguments for the function as as Dict
    :return:
    """
    args = (python_to_dbus(value, True) for value in args)

    if kwargs:
        result = dbus_con.Functions(str(function_name), 'user_console_is_True', *args, dict_to_dbus_kwargs(kwargs, True))
    else:
        result = dbus_con.Functions(str(function_name), 'user_console_is_True', *args)

    result = dbus_to_python(result, True)

    return result

def Variables(dbus_con, variable_name, *args):
    """
    The user friendly version to use the Variables method exported by all CCS applications via DBus, lets one change and
    get all Variables of a CCs application

    :param dbus_con: A Dbus connection
    :param variable_name: The variable
    :param args: The value to change the variable to, if nothing is given the value of the Variable is returned
    :return: Either the variable value or None if Variable was changed
    """
    args = (python_to_dbus(value, True) for value in args)

    result = dbus_con.Variables(str(variable_name), 'user_console_is_True', *args)

    result = dbus_to_python(result, True)

    return result

def Dictionaries(dbus_con, dictionary_name, *args):
    """
    The user friendly version to use the Dictionaries method exported by all CCS applications via DBus, lets one change
    and get values or the entire Dictionary for all availabe Dictionaries of a CCS application

    :param dbus_con: A Dbus connection
    :param dictionary_name: The dictionary name
    :param args: A key of the dictionary to get the corresponding value, or a key and a value to change the value for a
    key, if not given the entire dictionary is returned
    :return: The entire dictionary, a value for a given key or None if a value was changed
    """
    args = (python_to_dbus(value, True) for value in args)

    result = dbus_con.Dictionaries(str(dictionary_name), 'user_console_is_True', *args)

    result = dbus_to_python(result, True)

    return result

def dict_to_dbus_kwargs(arguments={}, user_console = False):
    """
    Converts a dictionary to kwargs dbus does understand and if necessary and requested changes NoneType to 'NoneType'

    :param arguments: The to converting dictionary
    :return: The dbus Dictionary which simulates the kwargs
    """
    if user_console:
        for key in arguments.keys():
            if arguments[key] is None:
                arguments[key] = 'NoneType'

    return dbus.Dictionary({'kwargs': dbus.Dictionary(arguments, signature='sv')})


# Converts dbus types to python types
def dbus_to_python(data, user_console=False):
    """
    Converts DBus types to Python types

    :param data: Dbus Type variables or containers
    :param user_console: Flag to check for NoneType arguments
    :return: Same data as python variables or containers
    """
    # NoneType string is transformed to a python None type
    if user_console and data == 'NoneType':
        data = None
    elif isinstance(data, dbus.String):
        data = str(data)
    elif isinstance(data, dbus.Boolean):
        data = bool(data)
    elif isinstance(data, (dbus.Int16, dbus.UInt16, dbus.Int32, dbus.UInt32, dbus.Int64, dbus.UInt64)):
        data = int(data)
    elif isinstance(data, dbus.Double):
        data = float(data)
    elif isinstance(data, dbus.Array):
        data = [dbus_to_python(value, user_console) for value in data]
    elif isinstance(data, dbus.Dictionary):
        new_data = dict()
        for key in data.keys():
            new_data[str(key)] = dbus_to_python(data[key], user_console)
        data = new_data
    elif isinstance(data, dbus.ByteArray):
        data = bytes(data)
    elif isinstance(data, dbus.Struct):
        result = tuple()
        for value in data:
            new = dbus_to_python(value, user_console)
            result = result + (new,)
        data = result
    return data


def python_to_dbus(data, user_console=False):
    """
    Converts Python Types to Dbus Types, only containers, since 'normal' data types are converted automatically by dbus

    :param data: Dbus Type variables or containers
    :param user_console: Flag to check for NoneType arguments
    :return: Same data for python variables, same data for container types as dbus containers
    """

    if user_console and data is None:
        data = dbus.String('NoneType')
    elif isinstance(data, list):
        data = dbus.Array([python_to_dbus(value, user_console) for value in data], signature='v')
    elif isinstance(data, dict):
        data = dbus.Dictionary(data, signature='sv')
        for key in data.keys():
            data[key] = python_to_dbus(data[key], user_console)
    elif isinstance(data, tuple):
        data = dbus.Struct([python_to_dbus(value, user_console) for value in data], signature='v')
    elif isinstance(data, (int, str, float, bool, bytes, bytearray)):
        pass
    else:
        logger.info("Object of type " + str(type(data)) + " can probably not be sent via dbus")
    return data


def convert_to_python(func):
    """
    The Function dbus_to_python can be used as a decorator where all return values are changed to python types

    :param func: The function where the decorator should be used
    :return: The wrapped function
    """
    def wrapper(*args, **kwargs):
        """

        :param args:
        :param kwargs:
        :return:
        """
        return dbus_to_python(func(*args, **kwargs))
    return wrapper


def set_monitor(pool_name=None, param_set=None):
    """

    :param pool_name:
    :param param_set:
    :return:
    """
    if is_open('monitor'):
        monitor = dbus_connection('monitor', communication['monitor'])
    else:
        # print('The Parmameter Monitor is not running')
        logger.error('The Parmameter Monitor is not running')
        return

    if pool_name is not None:
        monitor.Functions('set_pool', pool_name)
    else:
        # print('Pool Name has to be specified (cfl.set_monitor(pool_name, parmeter_set))')
        logger.error('Pool Name has to be specified (cfl.set_monitor(pool_name, parmeter_set))')
        return

    if param_set is not None:
        # Ignore_reply is ok here
        monitor.Functions('monitor_setup', param_set, ignore_reply=True)
    else:
        monitor.Functions('monitor_setup', ignore_reply=True)

    return


# def ptt_reverse(typ):
#
#     """
#     Returns the ptc location (first layer) of a Type stored in s2k_partypes 'ptt'
#     :param typ: Has to be a type given in s2k_partypes 'ptt'
#     :return: ptc location
#     """
#     if typ.startswith('oct'):
#         return [7, typ[3:]]
#     elif typ.startswith('ascii'):
#         return [8, typ[5:]]
#
#     for i in ptt: # First Section
#         for j in ptt[i]: # Second Section
#             if ptt[i][j] == typ: # Check for type
#                 return [i, j]
#
#     return False


def user_tm_decoders_func():
    """

    :return:
    """
    if cfg.has_section('ccs-user_defined_packets'):
        user_tm_decoders = {k: json.loads(cfg['ccs-user_defined_packets'][k]) for k in cfg['ccs-user_defined_packets']}
    else:
        user_tm_decoders = {}
    return user_tm_decoders


def Tmformatted(tm, separator='\n', sort_by_name=False, textmode=True, udef=False, nocal=False, floatfmt=None):
    """
    Return a formatted string containing all the decoded source data of TM packet _tm_

    :param tm:
    :param separator:
    :param sort_by_name:
    :param textmode:
    :param udef:
    :param nocal:
    :return:
    """
    sourcedata, tmtcnames = Tmdata(tm, udef=udef, floatfmt=floatfmt)
    tmtcname = " / ".join(tmtcnames)

    if nocal:
        # check if packet size is variable (because of different returned data structure)
        if not isinstance(sourcedata[0][-1], tuple):
            def _get_val_func(x):
                return [str(x[2]), str(x[4]), '']
        else:
            def _get_val_func(x):
                return [str(x[2]), str(x[4][0]), '']
    else:
        def _get_val_func(x):
            return [str(x[2]), str(x[0]), none_to_empty(x[1])]

    if textmode:
        if sourcedata is not None:
            formattedlist = ['{}:  {} {}'.format(*_get_val_func(i)) for i in sourcedata]
            if sort_by_name:
                formattedlist.sort()
        else:
            formattedlist = []
        return separator.join([Tm_header_formatted(tm)] + [tmtcname] + [100 * "-"] + formattedlist)
    else:
        if sourcedata is not None:
            try:
                formattedlist = [[*_get_val_func(i), parameter_tooltip_text(i[-1][0])] for i in sourcedata]
            # for variable length packets
            except (IndexError, TypeError):
                formattedlist = [[*_get_val_func(i), parameter_tooltip_text(i[-1])] for i in sourcedata]
        else:
            formattedlist = [[]]

        return formattedlist, tmtcname


##
#  TM source data
#
#  Decode source data field of TM packet
#  @param tm TM packet bytestring
def Tmdata(tm, udef=False, floatfmt=None):
    """

    :param tm:
    :param udef:
    :return:
    """
    tpsd = None
    params = None
    dbcon = scoped_session_idb

    # check if a UDEF exists and use to decode, if not the IDB will be checked
    if udef:
        try:
            header, data, crc = Tmread(tm)
            st, sst, apid = header.SERV_TYPE, header.SERV_SUB_TYPE, header.APID
            que = 'SELECT pic_pi1_off,pic_pi1_wid from pic where pic_type=%s and pic_stype=%s' % (st, sst)
            # que = 'SELECT pic_pi1_off,pic_pi1_wid from pic where pic_type=%s and pic_stype=%s and pic_apid=%s' % (st, sst, apid)
            dbres = dbcon.execute(que)
            pi1, pi1w = dbres.fetchall()[0]

            pi1val = int.from_bytes(tm[pi1:pi1 + pi1w//8], 'big')
            tag = '{}-{}-{}-{}'.format(st, sst, apid, pi1val)
            user_label, params = user_tm_decoders[tag]
            spid = None

            # Length of a parameter which should be decoded acording to given position
            if len(params[0]) == 9:
                vals_params = decode_pus(data, params)
            # Decode according to given order, length is then 11
            else:
                vals_params = read_variable_pckt(data, params)

            tmdata = [(get_calibrated(i[0], j[0], floatfmt=floatfmt), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]
            tmname = ['USER DEFINED: {}'.format(user_label)]

            return tmdata, tmname

        except Exception as err:
            logger.info('UDEF could not be found, search in IDB ({})'.format(err))
        finally:
            dbcon.close()

    try:

        if (tm[0] >> 4) & 1:
            return Tcdata(tm)

        header, data, crc = Tmread(tm)
        st, sst, apid = header.SERV_TYPE, header.SERV_SUB_TYPE, header.APID
        que = 'SELECT pic_pi1_off,pic_pi1_wid from pic where pic_type=%s and pic_stype=%s' % (st, sst)
        dbres = dbcon.execute(que)
        pi1, pi1w = dbres.fetchall()[0]

        if pi1 != -1:
            pi1val = int.from_bytes(tm[pi1:pi1 + pi1w//8], 'big')
            que = 'SELECT pid_spid,pid_tpsd,pid_dfhsize from pid where pid_type=%s and pid_stype=%s and ' \
                  'pid_apid=%s and pid_pi1_val=%s' % (st, sst, apid, pi1val)
        else:
            que = 'SELECT pid_spid,pid_tpsd,pid_dfhsize from pid where pid_type=%s and pid_stype=%s and ' \
                  'pid_apid=%s' % (st, sst, apid)

        dbres = dbcon.execute(que)
        fetch = dbres.fetchall()

        # if APID or SID does not match:
        if len(fetch) != 0:
            spid, tpsd, dfhsize = fetch[0]
        else:
            if (st, sst) != (3, 25):
                logger.info('APID {} not found for TM{},{} in I-DB -- not using APID'.format(apid, st, sst))
            if pi1 != -1:
                try:
                    tag = '{}-{}-{}-{}'.format(st, sst, apid, pi1val)
                    user_label, params = user_tm_decoders[tag]
                    spid = None
                except KeyError:
                    que = 'SELECT pid_spid,pid_tpsd,pid_dfhsize from pid where pid_type=%s and pid_stype=%s\
                           and pid_pi1_val=%s' % (st, sst, pi1val)
            else:
                que = 'SELECT pid_spid,pid_tpsd,pid_dfhsize from pid where pid_type=%s and pid_stype=%s' % (st, sst)
            if params is None:
                dbres = dbcon.execute(que)
                spid, tpsd, dfhsize = dbres.fetchall()[0]

        # TODO: proper handling of super-commutated parameters
        if tpsd == -1 and params is None:
            que = 'SELECT pcf.pcf_name,pcf.pcf_descr,plf_offby,plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,\
            pcf.pcf_unit,pcf.pcf_pid,pcf.pcf_width FROM plf LEFT JOIN pcf ON plf.plf_name=pcf.pcf_name WHERE \
            plf.plf_spid={} AND pcf_name NOT LIKE "DPTG%" AND pcf_name NOT LIKE "SCTG%" \
            ORDER BY plf_offby,plf_offbi'.format(spid)
            dbres = dbcon.execute(que)
            params = dbres.fetchall()
            vals_params = decode_pus(data, params)
            tmdata = [(get_calibrated(i[0], j[0], floatfmt=floatfmt), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]

        elif params is not None:
            # Length of a parameter which should be decoded according to given position
            if len(params[0]) == 9:
                vals_params = decode_pus(data, params)
            # Decode according to given order, length is then 11
            else:
                vals_params = read_variable_pckt(data, params)

            tmdata = [(get_calibrated(i[0], j[0], floatfmt=floatfmt), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]

        else:
            que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx,pcf.pcf_width,\
            pcf.pcf_unit,pcf.pcf_pid,vpd_pos,vpd_grpsize,vpd_fixrep from vpd left join pcf on \
            vpd.vpd_name=pcf.pcf_name where vpd_tpsd={} AND pcf_name NOT LIKE "DPTG%" \
            AND pcf_name NOT LIKE "SCTG%" ORDER BY vpd_pos'.format(tpsd)
            dbres = dbcon.execute(que)
            params_in = dbres.fetchall()

            vals_params = read_variable_pckt(data, params_in)
            tmdata = [(get_calibrated(i[0], j, floatfmt=floatfmt), i[6], i[1], pidfmt(i[7]), j) for j, i in vals_params]
            # tmdata = [(get_calibrated(i[0], j[0]), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]

        if spid is not None:
            dbres = dbcon.execute("SELECT pid_descr FROM pid WHERE pid_spid={}".format(spid))
            tmname = dbres.fetchall()[0]
        else:
            tmname = ['USER DEFINED: {}'.format(user_label)]

    except Exception as failure:
        raise Exception('Packet data decoding failed: ' + str(failure))

    finally:
        dbcon.close()

    return tmdata, tmname


def read_pus(data):
    """
    Read single PUS packet from buffer

    @param data: has to be peekable
    @return: single PUS packet as byte string or *None*
    """
    pus_size = data.peek(10)

    if len(pus_size) >= 6:
        pus_size = pus_size[4:6]
    elif 0 < len(pus_size) < 6:
        start_pos = data.tell()
        pus_size = data.read(6)[4:6]
        data.seek(start_pos)
    elif len(pus_size) == 0:
        return

    # packet size is header size (6) + pus size field + 1
    pckt_size = int.from_bytes(pus_size, 'big') + 7
    return data.read(pckt_size)


def extract_pus(data):
    """

    @param data:
    @return:
    """
    pckts = []
    if isinstance(data, bytes):
        data = io.BufferedReader(io.BytesIO(data))

    while True:
        pckt = read_pus(data)
        if pckt is not None:
            pckts.append(pckt)
        else:
            break
    return pckts


def extract_pus_brute_search(data, filename=None, trashcnt=None):
    """

    :param data:
    :param filename:
    :param trashcnt:
    :return:
    """
    pckts = []
    if trashcnt is None:
        trashcnt = {filename: 0}  # dummy counter if no trashcnt dict is given

    if isinstance(data, bytes):
        data = io.BufferedReader(io.BytesIO(data))
    elif isinstance(data, io.BufferedReader):
        pass
    else:
        raise TypeError('Cannot handle input of type {}'.format(type(data)))

    while True:
        pos = data.tell()
        pckt = read_pus(data)
        if pckt is not None:
            if not crc_check(pckt):
                pckts.append(pckt)
            else:
                data.seek(pos + 1)
                trashcnt[filename] += 1
        else:
            break

    return pckts


def unpack_pus(pckt, use_pktlen=False, logger=logger):
    """
    Decode PUS and return header parameters and data field

    :param pckt:
    :param use_pktlen: whether to use packet length info in header or just take all of the data after the header as payload
    :param logger:
    :return:
    """
    try:
        tmtc = pckt[0] >> 4 & 1
        dhead = pckt[0] >> 3 & 1

        if tmtc == 0 and dhead == 1 and (len(pckt) >= TM_HEADER_LEN):
            header = TMHeader()
            header.bin[:] = pckt[:TM_HEADER_LEN]
            if not use_pktlen:
                data = pckt[TM_HEADER_LEN:-PEC_LEN]
                crc = pckt[-PEC_LEN:]
            else:
                data = pckt[TM_HEADER_LEN:header.bits.PKT_LEN + 7 - PEC_LEN]
                crc = pckt[header.bits.PKT_LEN + 7 - PEC_LEN:header.bits.PKT_LEN + 7]

        elif tmtc == 1 and dhead == 1 and (len(pckt) >= TC_HEADER_LEN):
            header = TCHeader()
            header.bin[:] = pckt[:TC_HEADER_LEN]
            if not use_pktlen:
                data = pckt[TC_HEADER_LEN:-PEC_LEN]
                crc = pckt[-PEC_LEN:]
            else:
                data = pckt[TC_HEADER_LEN:header.bits.PKT_LEN + 7 - PEC_LEN]
                crc = pckt[header.bits.PKT_LEN + 7 - PEC_LEN:header.bits.PKT_LEN + 7]

        else:
            header = PHeader()
            header.bin[:P_HEADER_LEN] = pckt[:P_HEADER_LEN]
            if not use_pktlen:
                data = pckt[P_HEADER_LEN:]
            else:
                data = pckt[P_HEADER_LEN:header.bits.PKT_LEN + 7]
            crc = None

        head_pars = header.bits

    except Exception as err:
        logger.warning('Error unpacking PUS packet: {}\n{}'.format(pckt, err))
        head_pars = None
        data = None
        crc = None

    finally:
        return head_pars, data, crc


def decode_pus(tm_data, parameters, decode_tc=False):
    """

    :param tm_data:
    :param parameters:
    :param decode_tc:
    :return:
    """
    # checkedfmts = [fmtcheck(i[1]) for i in idb]
    # if not any(checkedfmts):
    # fmts = []
    # for par in parameters:
    #    if not par[4] in [7,8]:
    #        fmts.append(ptt[par[4]][par[5]])
    #    elif par[4] == 7:
    #        fmts.append('oct' + str(par[5]) + 's')
    #    elif par[4] == 8:
    #        fmts.append('ascii' + str(par[5]) + 's')
    if not decode_tc:
        fmts = [parameter_ptt_type_tm(par) for par in parameters]
    else:
        fmts = [parameter_ptt_type_tc_read(par) for par in parameters]

    try:
        return zip(struct.unpack('>' + ''.join(fmts), tm_data), parameters)
    except struct.error:
        tms = io.BytesIO(tm_data)
        if not decode_tc:
            return [(read_stream(tms, fmt, pos=par[2] - TM_HEADER_LEN, offbi=par[3]), par) for fmt, par in zip(fmts, parameters)]
        else:
            return [(read_stream(tms, fmt, pos=par[-1]/8, offbi=0 if par[5] % 8 == 0 else 8 - par[5] % 8), par) for fmt, par in zip(fmts, parameters)]


##
#  Read_stream
#
#  Reads out the imported Byte object
#  Returns the Unpackt parameter depending on the format of it
#  @param stream Input Bytes Object
#  @param fmt Input String that defines the format of the bytes
#  @param pos Input The BytePosition in the input bytes
#  @param offbi
def read_stream(stream, fmt, pos=None, offbi=0, none_on_fail=False):
    """

    :param stream:
    :param fmt:
    :param pos:
    :param offbi:
    :return:
    """
    if pos is not None:
        stream.seek(int(pos))

    readsize = csize(fmt, offbi)
    data = stream.read(readsize)

    if not data:
        if none_on_fail:
            logger.debug('No data left to read from [{}]!'.format(fmt))
            return
        else:
            raise BufferError('No data left to read from [{}]!'.format(fmt))

    if fmt == 'I24':
        x = int.from_bytes(data, 'big')
    elif fmt == 'i24':
        x = int.from_bytes(data, 'big', signed=True)
    # for bit-sized unsigned parameters:
    elif fmt.startswith('uint'):
        bitlen = int(fmt[4:])
        # bitsize = (bitlen // 8 + 1) * 8
        bitsize = len(data) * 8
        x = (int.from_bytes(data, 'big') & (2 ** (bitsize - offbi) - 1)) >> (bitsize - offbi - bitlen)
    elif fmt.startswith('oct'):
        x = struct.unpack('>{}s'.format(fmt[3:]), data)[0]
    elif fmt.startswith('ascii'):
        x = struct.unpack('>{}s'.format(fmt[5:]), data)[0]
        try:
            x = x.decode('ascii')
        except UnicodeDecodeError as err:
            logger.warning(err)
            x = x.decode('utf-8', errors='replace')
    elif fmt == timepack[0]:
        x = timecal(data)
    elif fmt.startswith('CUC'):
        x = timeformats.cuctime.get(fmt).calc_time(data)
    else:
        x = struct.unpack('>' + fmt, data)[0]

    return x


def csize(fmt, offbi=0, bitsize=False):
    """
    Returns the amount of bytes required for the input format

    :param fmt: Input String that defines the format
    :param offbi:
    :return:
    """

    if bitsize:
        bits = 8
    else:
        bits = 1

    if fmt in ('i24', 'I24'):
        return 3
    elif fmt.startswith('uint'):
        return (int(fmt[4:]) + offbi - 1) // 8 + 1
    elif fmt == timepack[0]:
        return timepack[1] - timepack[3]
    elif fmt.startswith('CUC'):
        try:
            return timeformats.cuctime.get(fmt).cize
        except AttributeError:
            raise NotImplementedError('Unknown format {}'.format(fmt))
    elif fmt.startswith('oct'):
        return int(fmt[3:])
    elif fmt.startswith('ascii'):
        return int(fmt[5:])
    else:
        try:
            return struct.calcsize(fmt)
        except struct.error:
            raise NotImplementedError('Unknown format {}'.format(fmt))


##
# parameter_ptt_type
#
# Returns the format of the input bytes for TM (list has to be formated the correct way)
# @param parameters Input List of one parameter
def parameter_ptt_type_tm(par):
    """

    :param par:
    :return:
    """
    return ptt(par[4], par[5])


##
# parameter_ptt_type
#
# Returns the format of the input bytes for TC (list has to be formated the correct way)
# @param parameters Input List of one parameter
def parameter_ptt_type_tc_read(par):
    """

    :param par:
    :return:
    """
    if par[2] is None:
        return ptt('SPARE_visible', par[5])
    else:
        return ptt(par[2], par[3])


##
#  Nonetoempty
#
#  Return empty string "" if input is _None_, else return input string
#  @param s Input string
def none_to_empty(s):
    """

    :param s:
    :return:
    """
    return '' if s is None else s


def str_to_int(itr):
    """

    :param itr:
    :return:
    """
    return int(itr) if itr.lower() != 'none' else None


def Tm_header_formatted(tm, detailed=False):
    """

    :param tm:
    :param detailed:
    :return:
    """

    # if len(tm) < TC_HEADER_LEN:
    #     return 'Cannot decode header - packet has only {} bytes!'.format(len(tm))
    # params = list(struct.unpack('>HHHBBB', tm[:9]))
    # params[0] &= 2047
    # params[1] &= 16383
    # del (params[3])

    head = Tmread(tm)[0]
    if head is None:
        return 'Cannot decode header - packet has only {} bytes!'.format(len(tm))

    if detailed:
        hparams = get_header_parameters_detailed(tm)
        hlist = '\n'.join(['{}: {}'.format(par, val) for par, val in hparams])
        details = '\n\n{}\n\n{}'.format(hlist, head._b_base_.raw.hex().upper())
    else:
        details = ''

    if head.PKT_TYPE == 1:
        return 'APID:{}|SEQ:{}|LEN:{}|TYPE:{}|STYPE:{}{}'.format(head.APID, head.PKT_SEQ_CNT, head.PKT_LEN,
                                                               head.SERV_TYPE, head.SERV_SUB_TYPE, details)
    else:
        return 'APID:{}|SEQ:{}|LEN:{}|TYPE:{}|STYPE:{}|CUC:{}{}'.format(
            head.APID, head.PKT_SEQ_CNT, head.PKT_LEN, head.SERV_TYPE, head.SERV_SUB_TYPE, mkcucstring(tm), details)


def spw_header_formatted(spw_header):
    """

    :param spw_header:
    :return:
    """
    buf = spw_header.__class__.__name__ + '\n\n'
    buf += spw_header.raw.hex()
    return buf


def get_header_parameters_detailed(pckt):
    """
    Return values of all header elements

    :param pckt:
    """
    head = Tmread(pckt)[0]
    hparams = [(x[0], getattr(head, x[0])) for x in head._fields_]
    return hparams


##
# CUC timestring
#
#  Generate timestring (seconds.microseconds) with (un-)synchronised flag (U/S) appended from TM packet (header data)
#  @param tml List of decoded TM packet header parameters or TM packet
def mkcucstring(tml):
    """

    :param tml:
    :return:
    """
    return timecal(tml[CUC_OFFSET:CUC_OFFSET+timepack[1]], string=True)


def get_cuc_now():
    """
    Returns the current UTC time in seconds since the reference epoch

    :return:
    """
    cuc = datetime.datetime.now(datetime.timezone.utc) - CUC_EPOCH
    return cuc.total_seconds()


def utc_to_cuc(utc):
    """
    Returns the time provided in seconds since the reference epoch

    :param utc: ISO formatted date-time string or timezone aware datetime object
    :return:
    """
    if isinstance(utc, str):
        cuc = datetime.datetime.fromisoformat(utc) - CUC_EPOCH
    else:
        cuc = utc - CUC_EPOCH
    return cuc.total_seconds()


def cuc_to_utc(cuc):
    """
    Returns the UTC date-time corresponding to the provided second offset from the reference epoch

    :param cuc: Seconds since the reference epoch
    :return:
    """
    utc = CUC_EPOCH + datetime.timedelta(seconds=cuc)
    return utc.isoformat()


def cuc_time_str(head, logger=logger):
    """
    Return PUS header timestamp as string

    :param head: TMHeader instance
    :param logger:
    :return:
    """
    try:
        if head.PKT_TYPE == 0 and head.SEC_HEAD_FLAG == 1:
            if head.TIMESYNC in tsync_flag:
                return '{:.6f}{}'.format(head.CTIME + head.FTIME / timepack[2], tsync_flag[head.TIMESYNC])
            else:
                logger.warning('Unknown timesync flag value {} in packet {}'.format(head.TIMESYNC, head.raw[:4].hex()))
                return '{:.6f}{}'.format(head.CTIME + head.FTIME / timepack[2], 'U')
        else:
            return ''
    except Exception as err:
        logger.warning(err)
        return '#######'


##
#  Parametertooltiptext
#
#  Takes numerical value and returns corresponding hex and decimal values as a string.
#  Intended for parameter view tooltips.
def parameter_tooltip_text(x):
    """

    :param x:
    :return:
    """
    if isinstance(x, int):
        h = hex(x)[2:].upper()
        if np.sign(x) == -1:
            h = hex(x)[3:].upper()
    elif isinstance(x, float):
        h = struct.pack('>f', x).hex().upper()
    elif isinstance(x, bytes):
        return x.hex().upper()
    else:
        # h = str(x)
        return str(x)
    return 'HEX: 0x{}\nDEC: {}'.format(h, x)


def Tcdata(tm):
    """

    :param tm:
    :return:
    """
    header, data, crc = Tmread(tm)
    st, sst, apid = header.SERV_TYPE, header.SERV_SUB_TYPE, header.APID
    dbcon = scoped_session_idb

    # check if TC contains fixed value parameter for discrimination
    que = 'SELECT ccf_cname,cdf_bit,cdf_value,cpc_ptc,cpc_pfc, cpc_pafref FROM ccf LEFT JOIN cdf ON ccf_cname=cdf_cname ' \
          'LEFT JOIN cpc ON cdf_pname=cpc_pname WHERE ccf_type={} AND ccf_stype={} AND ccf_apid={} AND cdf_eltype="F"'.format(st, sst, apid)

    finfo = dbcon.execute(que).fetchall()
    if finfo:
        cname, offbit, cdfval, ptc, pfc, paf = finfo[0]
        fvalue = read_stream(io.BytesIO(data), ptt(ptc, pfc), pos=offbit // 8)

        for paf in [info[-1] for info in finfo]:
            fname = tc_param_alias_reverse(paf, None, fvalue)
            if fname != fvalue:
                break
        try:
            cname = [p[0] for p in finfo if p[2] == fname][0]
        except IndexError:
            raise ValueError('Unknown discriminant: {}'.format(fvalue))

        que = 'SELECT ccf_cname, ccf_descr, cpc_ptc, cpc_pfc, ccf_npars, cdf_ellen, cdf_pname, cpc_descr,cpc_prfref,' \
              ' cpc_pafref, cpc_ccaref, cdf_grpsize, cdf_bit FROM ccf left join cdf on ccf_cname=cdf_cname left join' \
              ' cpc on cdf_pname=cpc_pname where ccf_cname="{}" order by cdf_bit, ccf_cname'.format(cname)

    else:
        que = 'SELECT ccf_cname, ccf_descr, cpc_ptc, cpc_pfc, ccf_npars, cdf_ellen, cdf_pname, cpc_descr,\
             cpc_prfref, cpc_pafref, cpc_ccaref, cdf_grpsize, cdf_bit FROM ccf left join cdf on \
             ccf_cname=cdf_cname left join cpc on cdf_pname=cpc_pname where\
             ccf_type={} and ccf_stype={} and ccf_apid={} order by cdf_bit, ccf_cname'.format(st, sst, apid)

    # TODO: project agnostic implementation for decoding ambiguous TCs

    params = dbcon.execute(que).fetchall()

    if len(params) == 0:
        #dbres = dbcon.execute(
        #    'SELECT ccf_cname, ccf_descr, cpc_ptc, cpc_pfc, ccf_npars, cdf_ellen, cdf_pname, cpc_descr, cpc_prfref,\
        #     cpc_pafref, cpc_ccaref, cdf_grpsize, 0 FROM ccf left join cdf on ccf_cname=cdf_cname left join cpc on\
        #     cdf_pname=cpc_pname where ccf_type={} and ccf_stype={}'.format(st, sst))
        dbres = dbcon.execute(
            'SELECT ccf_cname, ccf_descr, cpc_ptc, cpc_pfc, ccf_npars, cdf_ellen, cdf_pname, cpc_descr, cpc_prfref,\
             cpc_pafref, cpc_ccaref, cdf_grpsize, cdf_bit FROM ccf left join cdf on ccf_cname=cdf_cname left join cpc on\
             cdf_pname=cpc_pname where ccf_type={} and ccf_stype={}'.format(st, sst))

        params = dbres.fetchall()

    dbcon.close()
    tcnames = list({x[1] for x in params})

    # return if no TC can be unambiguously assigned
    _npars = {x[4] for x in params}
    if len(tcnames) and len(_npars) > 1:
        tcdata = None
        tcnames.append("\n\nAmbiguous packet type - cannot decode.")
        return tcdata, tcnames

    # select one parameter set if IFSW and DBS have entry
    if len(tcnames) > 1:
        params = params[::len(tcnames)]
    if params[0][4] == 0:
        return None, tcnames
    # check for ambiguity in CCF table and choose a version
    # params = [x for x in params if x[0] == params[-1][0]]

    # check for spare parameters and insert format info
    for par in params:
        if par[2] is None:
            newpar = list(par)
            newpar[2] = 'SPARE_visible'
            newpar[3] = par[5]
            newpar[7] = 'Spare{}'.format(par[5])
            params[params.index(par)] = newpar

    # check for variable length packet
    var_len = any([p[-2] for p in params])

    if not var_len:
        #extr_fmt = ','.join([ptt[p[2]][p[3]] for p in params]) ### only 2010/6 key error 20
        try:
            #vals_params = data.unpack(extr_fmt)
            # The Parameters needed are on different locations for TM and TC but for read_variable_pct they need to have this order, therefor we change the order of the list shortly and than change it back
            vals_params = decode_pus(data, params, decode_tc=True)

        except IndexError:
            vals_params = None
            #print(traceback.format_exc())
    else:
        #repeat = 0
        #outlist = []
        #datastream = BitStream(data)
        try:
            vals_params = read_variable_pckt(data, params, tc=True)
        except IndexError:
            vals_params = None
    if vals_params:
        tcdata = [(tc_param_alias_reverse(*p[9:11], val, p[6]), None, p[7], val) for val, p in vals_params]
        #tcdata = [(tc_param_alias_reverse(*p[9:11], val, p[6]), None, p[7], val) for p, val in zip(params, o)]
        #print(tcdata)
    else:
        tcdata = None
        tcnames.append("\n\nAmbiguous packet type - cannot decode.")
    return tcdata, tcnames


# Decode TM bytestring into list of TM packet values
#   @param pckt TM bytestring
def Tmread(pckt):
    """

    :param pckt:
    :return:
    """
    return unpack_pus(pckt)
    # try:
    #     tmtc = pckt[0] >> 4 & 1
    #     dhead = pckt[0] >> 3 & 1
    #
    #     if tmtc == 0 and dhead == 1 and (len(pckt) >= TM_HEADER_LEN):
    #         header = TMHeader()
    #         header.bin[:] = pckt[:TM_HEADER_LEN]
    #         data = pckt[TM_HEADER_LEN:-PEC_LEN]
    #         crc = pckt[-PEC_LEN:]
    #
    #     elif tmtc == 1 and dhead == 1 and (len(pckt) >= TC_HEADER_LEN):
    #         header = TCHeader()
    #         header.bin[:] = pckt[:TC_HEADER_LEN]
    #         data = pckt[TC_HEADER_LEN:-PEC_LEN]
    #         crc = pckt[-PEC_LEN:]
    #
    #     else:
    #         header = TCHeader()
    #         header.bin[:P_HEADER_LEN] = pckt[:P_HEADER_LEN]
    #         data = pckt[P_HEADER_LEN:]
    #         crc = None
    #
    #     head_pars = header.bits
    #
    # except Exception as err:
    #     # print('Error unpacking packet: {}\n{}'.format(pckt, err))
    #     logger.warning('Error unpacking packet: {}\n{}'.format(pckt, err))
    #     head_pars = None
    #     data = None
    #     crc = None
    #
    # finally:
    #     return head_pars, data, crc


##
#  Generate (space separated) hexstring from byte/bitstring
#  @param inbytes   bytestring or bitstring object to be converted
#  @param separator string by which the hex doublettes are joined, default=' '
def prettyhex(inbytes, separator=' '):
    """

    :param inbytes:
    :param separator:
    :return:
    """
    if not isinstance(inbytes, bytes):
        inbytes = inbytes.bytes
    return separator.join(['%02X' % x for x in inbytes])


##
#  Varpack
#
#  Decode variable-length part of TM/TC source data
#  @param data    input data of bitstring.BitStream type
#  @param parameters  list of parameter properties present in data
#  @param paramid parameter counter
#  @param outlist list of decoded source data parameter values
#  @param parlist list of decoded source data parameter properties
def read_varpack(data, parameters, paramid, outlist, parlist):
    """

    :param data:
    :param parameters:
    :param paramid:
    :param outlist:
    :param parlist:
    :return:
    """
    while paramid < len(parameters):
        fmt = ptt(parameters[paramid][2], parameters[paramid][3])
        if parameters[paramid][2] == 11:  # TODO: handle deduced parameter types
            raise NotImplementedError('Deduced parameter type PTC=11')
            # fmt = fmt[ptype]
            # if ptype == 7:  # ptt fmt string for bool not parsable with .read
            #     fmt = 'uint8'
        outdata = data.read(fmt)
        grpsize = parameters[paramid][-2]
        if parameters[paramid][6] == FMT_TYPE_PARAM:
            ptype = outdata
        outlist.append(outdata)
        parlist.append(parameters[paramid])

        if grpsize == 0:
            paramid += 1
        else:
            if parlist[-1][-1] == 0:
                repeat = outlist[-1]
            else:
                repeat = parlist[-1][-1]
                data.pos -= parlist[-1][5]
                # delete counter entry from lists
                outlist.pop(-1)
                parlist.pop(-1)

            while repeat > 0:
                outlist, parlist = read_varpack(data, parameters[paramid + 1:paramid + grpsize + 1], 0,
                                                outlist, parlist)
                repeat -= 1
            paramid += grpsize + 1
    return outlist, parlist


def read_variable_pckt(tm_data, parameters, tc=False):
    """
    Read parameters from a variable length packet

    :param tm_data:
    :param parameters:
    :return:
    """
    tms = io.BytesIO(tm_data)
    result = []

    result = read_stream_recursive(tms, parameters, decoded=result, tc=tc)

    return result


def read_stream_recursive(tms, parameters, decoded=None, bit_off=0, tc=False):
    """
    Recursively operating function for decoding variable length packets

    :param tms:
    :param parameters:
    :param decoded:
    :param bit_off:
    :param tc:
    :return:
    """

    decoded = [] if decoded is None else decoded

    skip = 0
    for par_idx, par in enumerate(parameters):
        if skip > 0:
            skip -= 1
            continue
        grp = par[-2]

        if grp is None:  # None happens for UDEF
            grp = 0

        fmt = ptt(par[2], par[3])
        if fmt == 'deduced':
            raise NotImplementedError('Deduced parameter type PTC=11')

        fixrep = par[-1]

        # don't use fixrep in case of a TC, since it is only defined for TMs
        if grp and fixrep and not tc:
            value = fixrep
            logger.debug('{} with fixrep={} used'.format(par[1], value))
        else:
            bits = par[5]
            unaligned = bits % 8

            value = read_stream(tms, fmt, offbi=bit_off)

            bit_off = (bit_off + unaligned) % 8
            # re-read byte if read position is bit-offset after previous parameter
            if bit_off:
                tms.seek(tms.tell() - 1)

            decoded.append((value, par))

        if grp != 0:
            skip = grp
            rep = value
            while rep > 0:
                decoded = read_stream_recursive(tms, parameters[par_idx + 1:par_idx + 1 + grp], decoded, bit_off=bit_off, tc=tc)
                rep -= 1

    return decoded


def tc_param_alias_reverse(paf, cca, val, pname=None):
    """

    :param paf:
    :param cca:
    :param val:
    :param pname:
    :return:
    """
    if paf is not None:
        dbcon = scoped_session_idb
        que = 'SELECT pas_altxt from pas where pas_numbr="%s" and pas_alval="%s"' % (paf, val)
        dbres = dbcon.execute(que)
        alval = dbres.fetchall()
        dbcon.close()
        if len(alval) == 0:
            return val
        return alval[0][0]
    elif cca is not None:
        dbcon = scoped_session_idb
        que = 'SELECT ccs_xvals,ccs_yvals from ccs where ccs_numbr="%s"' % (cca)
        dbres = dbcon.execute(que)
        xvals, yvals = np.array([x for x in zip(*dbres.fetchall())], dtype=float)
        dbcon.close()
        alval = np.interp(val, yvals, xvals)
        return alval
    # get name for ParamID if datapool item (in MIB)
    elif pname in DATA_POOL_ID_PARAMETERS:
        return get_pid_name(pidfmt_reverse(val))
    else:
        return val


def get_pid_name(pid):
    """

    :param pid:
    :return:
    """
    # if isinstance(pid, str):
    #     return pid
    if isinstance(pid, int):
        pids = [pid]

    try:
        names = [DP_IDS_TO_ITEMS[p] for p in pids]
    except KeyError as err:
        logger.warning('Unknown datapool ID')
        raise err

    # if pid in DP_IDS_TO_ITEMS:
    #     return DP_IDS_TO_ITEMS[pid]
    # else:
    #     logger.warning('Unknown datapool ID: {}'.format(pid))
    #     return pid
    return names if len(names) > 1 else names[0]


##
#  Format PID from I-DB value to int
def pidfmt(val):
    """

    :param val:
    :return:
    """
    return int(val - pid_offset) if val is not None else None


def pidfmt_reverse(val):
    """

    :param val:
    :return:
    """
    return int(val + pid_offset) if val is not None else None


## Parameter calibration
#  Calibrate raw parameter values
#  @param pcf_name PCF_NAME
#  @param rawval   Raw value of the parameter
def get_calibrated(pcf_name, rawval, properties=None, numerical=False, dbcon=None, nocal=False, floatfmt=None):
    """

    :param pcf_name:
    :param rawval:
    :param properties:
    :param numerical:
    :param dbcon:
    :param nocal:
    :return:
    """

    if rawval is None:
        return

    if properties is None:

        # cache
        if pcf_name in _pcf_cache:
            if _pcf_cache[pcf_name] is None:
                return rawval if isinstance(rawval, (int, float, str, bytes)) else rawval[0]
            else:
                ptc, pfc, categ, curtx = _pcf_cache[pcf_name]

        else:
            que = 'SELECT pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_categ,pcf.pcf_curtx from pcf where pcf_name="%s"' % pcf_name
            dbres = scoped_session_idb.execute(que)
            fetch = dbres.fetchall()
            scoped_session_idb.close()
            if len(fetch) == 0:
                _pcf_cache[pcf_name] = None
                return rawval if isinstance(rawval, (int, float, str, bytes)) else rawval[0]

            ptc, pfc, categ, curtx = fetch[0]
            _pcf_cache[pcf_name] = (ptc, pfc, categ, curtx)

    else:
        ptc, pfc, categ, curtx = properties

    try:
        type_par = ptt(ptc, pfc)
    except NotImplementedError:
        try:
            return rawval if isinstance(rawval, (int, float)) else rawval[0]
        except IndexError:
            return rawval

    if type_par == timepack[0]:
        return timecal(rawval)
    # elif categ == 'T' or type_par.startswith('ascii'):
    #     return rawval
    elif type_par.startswith('oct'):
        return rawval.hex().upper()
    elif curtx is None:
        if not nocal and cal is not None:
            calval = cal.calibrate_ext(rawval, pcf_name_to_descr(pcf_name))
            return calval if floatfmt is None else format(calval, floatfmt)
        try:
            return rawval if isinstance(rawval, (int, float)) else rawval[0]
        except IndexError:
            return rawval
    elif curtx is not None and categ == 'N':
        if nocal:
            return rawval
        else:
            return get_cap_yval(pcf_name, rawval) if floatfmt is None else format(get_cap_yval(pcf_name, rawval), floatfmt)
    elif curtx is not None and categ == 'S':
        if numerical or nocal:
            return rawval
        return get_txp_altxt(pcf_name, rawval)
    else:
        return rawval


##
#  Numerical calibration
#
#  Calibrate raw parameter values
#  @param pcf_name PCF_NAME
#  @param xval     Raw value of the parameter
def get_cap_yval(pcf_name, xval, properties=None, dbcon=None):
    """

    :param pcf_name:
    :param xval:
    :param properties:
    :param dbcon:
    :return:
    """

    # cache
    if pcf_name in _cap_cache:
        if _cap_cache[pcf_name] is None:
            return xval
        xvals, yvals = _cap_cache[pcf_name]

    else:
        que = 'SELECT cap.cap_xvals,cap.cap_yvals from pcf left join cap on pcf.pcf_curtx=cap.cap_numbr\
                where pcf.pcf_name="%s"' % pcf_name
        dbres = scoped_session_idb.execute(que)

        try:
            xvals, yvals = np.array([x for x in zip(*dbres.fetchall())], dtype=float)
            if np.isnan(xvals).any() or np.isnan(yvals).any():
                logger.error('Error in CAP support points for {}'.format(pcf_name))
                _cap_cache[pcf_name] = None
                return xval
            sortidx = xvals.argsort()
            xvals, yvals = xvals[sortidx], yvals[sortidx]  # make sure value pairs are sorted in x-ascending order
            _cap_cache[pcf_name] = (xvals, yvals)
        except IndexError:
            return xval
        finally:
            scoped_session_idb.close()

    yval = np.interp(xval, xvals, yvals, left=np.nan, right=np.nan)  # return NAN if outside defined calibration range

    # if yval == np.nan:
    #     logger.info('Calibration of {} failed. Value {} outside calibrated range {}-{}'.format(pcf_name, xval, xvals.min(), xvals.max()))

    return yval  # format(yval, 'g')


##
#  Textual calibration
#
#  Calibrate raw parameter values
#  @param pcf_name PCF_NAME
#  @param alval    Raw value of the parameter
def get_txp_altxt(pcf_name, alval, dbcon=None):
    """

    :param pcf_name:
    :param alval:
    :param dbcon:
    :return:
    """

    # cache
    if (pcf_name, alval) in _txp_cache:
        altxt = _txp_cache[(pcf_name, alval)]
        return altxt

    dbcon = scoped_session_idb
    que = 'SELECT txp.txp_altxt from pcf left join txp on pcf.pcf_curtx=txp.txp_numbr where\
            pcf.pcf_name="%s" and txp.txp_from=%s' % (pcf_name, alval if isinstance(alval, int) else alval[0])
    dbres = dbcon.execute(que)
    try:
        altxt, = dbres.fetchall()[0]
        _txp_cache[(pcf_name, alval)] = altxt
    except IndexError:
        altxt = alval
    finally:
        dbcon.close()
    return altxt


##
#  Dump list of TM packets
#
#  Save list of TM packets to file as either "binary" or "hex"
#  @param filename  Path to file
#  @param tmlist    List of TM packets
#  @param mode      Save as "binary" file or "hex" values with one packet per line
#  @param st_filter Save only packets of this service type
def Tmdump(filename, tmlist, mode='hex', st_filter=None, check_crc=False):
    """

    :param filename:
    :param tmlist:
    :param mode:
    :param st_filter:
    :param check_crc:
    """
    if st_filter is not None:
        tmlist = Tm_filter_st(tmlist, **st_filter)

    if check_crc:
        tmlist = (tm for tm in tmlist if not crc_check(tm))

    if mode.lower() == 'hex':
        with open(filename, 'w') as f:
            f.write('\n'.join([prettyhex(tm) for tm in tmlist]))
    elif mode.lower() == 'binary':
        if isinstance(tmlist, types.GeneratorType):
            with open(filename, 'wb') as f:
                for tm in tmlist:
                    f.write(tm)
        else:
            with open(filename, 'wb') as f:
                f.write(b''.join(tmlist))
    elif mode.lower() == 'text':
        txtlist = []
        for tm in tmlist:
            try:
                txtlist.append(Tmformatted(tm, separator='; '))
            except Exception as err:
                # logger.warning(err)
                txtlist.append(Tm_header_formatted(tm) + '; ' + str(tm[TM_HEADER_LEN:]))
        with open(filename, 'w') as f:
            f.write('\n'.join(txtlist))


def Tm_filter_st(tmlist, st=None, sst=None, apid=None, sid=None, time_from=None, time_to=None):
    """
    From tmlist return list of packets that match the specified criteria

    :param tmlist:
    :param st:
    :param sst:
    :param apid:
    :param sid:
    :param time_from:
    :param time_to:
    :return:
    """

    if st is not None:
        tmlist = [tm for tm in tmlist if tm[7] == st]

    if sst is not None:
        tmlist = [tm for tm in tmlist if tm[8] == sst]

    if apid is not None:
        # tmlist = [tm for tm in list(tmlist) if ((struct.unpack('>H', tm[:2])[0] & 2047) == apid)]
        tmlist = [tm for tm in list(tmlist) if (int.from_bytes(tm[:2], 'big') & 0x7FF) == apid]

    if sid:
        if st is None or sst is None or apid is None:
            raise ValueError('Must provide st, sst and apid if filtering by sid')

        sid_offset, sid_bitlen = get_sid(st, sst, apid)
        tobyte = sid_offset + sid_bitlen // 8
        tmlist = [tm for tm in list(tmlist) if int.from_bytes(tm[sid_offset:tobyte], 'big') == sid]

    if time_from is not None:
        tmlist = [tm for tm in list(tmlist) if (time_from <= get_cuctime(tm))]

    if time_to is not None:
        tmlist = [tm for tm in list(tmlist) if (get_cuctime(tm) <= time_to)]

    return tmlist


def filter_rows(rows, st=None, sst=None, apid=None, sid=None, time_from=None, time_to=None, idx_from=None, idx_to=None,
                tmtc=None, get_last=False):
    """
    Filter SQL query object by any of the given arguments, return filtered query.

    :param rows:
    :param st:
    :param sst:
    :param apid:
    :param sid:
    :param time_from:
    :param time_to:
    :param idx_from:
    :param idx_to:
    :param tmtc:
    :param get_last:
    """

    if st is not None:
        rows = rows.filter(DbTelemetry.stc == st)

    if sst is not None:
        rows = rows.filter(DbTelemetry.sst == sst)

    if apid is not None:
        rows = rows.filter(DbTelemetry.apid == apid)

    if sid:
        if st is None or sst is None or apid is None:
            raise ValueError('Must provide st, sst and apid if filtering by sid')

        sid_offset, sid_bitlen = get_sid(st, sst, apid)
        if sid_offset != -1:
            sid_size = sid_bitlen // 8
            rows = rows.filter(
                func.mid(DbTelemetry.data, sid_offset - TM_HEADER_LEN + 1, sid_size) == sid.to_bytes(sid_size, 'big'))
        else:
            logger.error('SID ({}) not applicable for {}-{}-{}'.format(sid, st, sst, apid))

    if time_from is not None:
        rows = rows.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) >= time_from)

    if time_to is not None:
        rows = rows.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) <= time_to)

    if idx_from is not None:
        rows = rows.filter(DbTelemetry.idx >= idx_from)

    if idx_to is not None:
        rows = rows.filter(DbTelemetry.idx <= idx_to)

    if tmtc is not None:
        rows = rows.filter(DbTelemetry.is_tm == tmtc)

    if get_last:
        rows = rows.order_by(DbTelemetry.idx.desc()).first()

    return rows


def filter_by_discr(rows, pi1_off, pi1_wid, pi1_val):
    """

    :param rows:
    :param pi1_off:
    :param pi1_wid:
    :param pi1_val:
    :return:
    """

    if not isinstance(pi1_val, bytes):
        pi1_val = pi1_val.to_bytes(pi1_wid, 'big')

    rows = rows.filter(func.mid(DbTelemetry.raw, pi1_off + 1, pi1_wid) == pi1_val)
    return rows


##
#  CRC check
#
#  Perform a CRC check on the _packet_. Returns True if CRC!=0.
#  @param packet TM/TC packet or any bytestring or bitstring object to be CRCed.
def crc_check(packet):
    """
    This function returns *True* if the CRC result is non-zero

    :param packet:
    :return:
    """
    return bool(crc(packet))


def get_cuctime(tml):
    """

    :param tml:
    :return:
    """
    cuc_timestamp = None
    if tml is not None:
        if isinstance(tml, bytes):
            return timecal(tml[CUC_OFFSET:CUC_OFFSET + timepack[1]], string=False)
            #ct, ft = struct.unpack('>IH', tml[TM_HEADER_LEN - 7:TM_HEADER_LEN - 1])
            #ft >>= 1
        elif isinstance(tml, pc.TMHeaderBits):
            ct = tml.CTIME
            ft = tml.FTIME
        elif isinstance(tml, list):
            if isinstance(tml[0], tuple):
                ct = tml[0][0][13]
                ft = tml[0][0][14]
            else:
                ct, ft = tml[13:15]
        elif isinstance(tml, tuple):
            ct = tml[0][13]
            ft = tml[0][14]
        else:
            raise TypeError("Can't handle input of type '{}'".format(type(tml)))

        # calculate the timestamp
        # the fine time, consisting out of 2 octets (2x 8bit), has a resolution of 2^16 - 1 bit = 2^15
        resolution = timepack[2]
        if ft > resolution:
            logger.warning('get_cuctime: the finetime value {} is larger than its resolution of {}'.format(ft, resolution))
            raise ValueError(
                'get_cuctime: the finetime value {} is larger than its resolution of {}'.format(ft, resolution))

        cuc_timestamp = ct + ft / resolution

    return cuc_timestamp


def get_pool_rows(pool_name, check_existence=False):
    """

    :param pool_name:
    :param check_existence:
    :return:
    """
    dbcon = scoped_session_storage()

    if check_existence:
        check = dbcon.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name)
        if not check.count():
            dbcon.close()
            raise ValueError('Pool "{}" does not exist.'.format(pool_name))

    rows = dbcon.query(
        DbTelemetry
    ).join(
        DbTelemetryPool,
        DbTelemetry.pool_id == DbTelemetryPool.iid
    ).filter(
        DbTelemetryPool.pool_name == pool_name
    )

    dbcon.close()

    return rows


def get_hk_val(pool_name, sid, par_id, apid=None):

    assert isinstance(sid, int)

    dbcon = scoped_session_idb()
    apid_filt = '' if apid is None else ' AND pid_apid={:d}'.format(apid)
    res = dbcon.execute('SELECT pid_descr FROM pid WHERE pid_type=3 and pid_stype=25 and pid_pi1_val={:d}{}'.format(sid, apid_filt)).fetchall()
    dbcon.close()

    if not res:
        return

    hk, = res[0]
    # TODO: user defined HKs

    if isinstance(par_id, int):
        pass  # TODO

    return get_param_values(pool_name=pool_name, hk=hk, param=par_id, last=1, mk_array=False)


# get values of parameter from HK packets
def get_param_values(tmlist=None, hk=None, param=None, last=0, numerical=False, tmfilter=True, pool_name=None, mk_array=True, nocal=False):
    """

    :param tmlist:
    :param hk:
    :param param:
    :param last:
    :param numerical:
    :param tmfilter:
    :param pool_name:
    :param mk_array:
    :param nocal:
    :return:
    """
    if param is None:
        return

    if tmlist is None and pool_name is not None:
        tmlist = get_pool_rows(pool_name, check_existence=True)

    dbcon = scoped_session_idb()
    if hk is None:
        que = 'SELECT plf.plf_name,plf.plf_spid,plf.plf_offby,plf.plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_unit,\
                   pcf.pcf_descr,pid.pid_apid,pid.pid_type,pid.pid_stype,pid.pid_descr,pid.pid_pi1_val from pcf\
                   left join plf on pcf.pcf_name=plf.plf_name left join pid on pid.pid_spid=plf.plf_spid\
                   where plf.plf_name="{}"'.format(param)
        dbres = dbcon.execute(que)
        name, spid, offby, offbi, ptc, pfc, unit, descr, apid, st, sst, hk, sid = dbres.fetchall()[0]
        if not isinstance(tmlist, list):
            tmlist_rows = filter_rows(tmlist, st=st, sst=sst, apid=apid, sid=sid)
            if tmlist_rows is not None:
                if last > 1:
                    tmlist = [tm.raw for tm in tmlist_rows.yield_per(1000)[-last:]]
                else:
                    tmlist = [tmlist_rows.order_by(DbTelemetry.idx.desc()).first().raw]
            else:
                tmlist = []
        else:
            sid = None if sid == 0 else sid

        ufmt = ptt(ptc, pfc)

    elif hk != 'User defined' and not hk.startswith('UDEF|'):
        que = 'SELECT pid_descr, pid_type,pid_stype,pid_pi1_val,pid_apid,plf.plf_name,plf.plf_spid,plf.plf_offby,plf.plf_offbi,\
                   pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_unit,pcf.pcf_descr,pcf.pcf_pid from pid left join plf on\
                   pid.pid_spid=plf.plf_spid left join pcf on plf.plf_name=pcf.pcf_name where\
                   pcf.pcf_descr="%s" and pid.pid_descr="%s"' % (param, hk)
        dbres = dbcon.execute(que)
        hkdescr, st, sst, sid, apid, name, spid, offby, offbi, ptc, pfc, unit, descr, pid = dbres.fetchall()[0]

        sid = None if sid == 0 else sid
        ufmt = ptt(ptc, pfc)

    elif hk.startswith('UDEF|'):
        label = hk.replace('UDEF|', '')
        hkref = [k for k in user_tm_decoders if user_tm_decoders[k][0] == label][0]
        pktinfo = user_tm_decoders[hkref][1]
        parinfo = [x for x in pktinfo if x[1] == param][0]
        pktkey = hkref.split('-')

        st = int(pktkey[0])
        sst = int(pktkey[1])
        apid = int(pktkey[2]) if pktkey[2] != 'None' else None
        sid = int(pktkey[3]) if pktkey[3] != 'None' else None
        # name, descr, _, offbi, ptc, pfc, unit, _, bitlen = parinfo
        name, descr, ptc, pfc, curtx, bitlen, unit, _, _, _, _ = parinfo
        if name in ['user_defined', 'user_defined_nopos', 'dp_item']:
            unit = None
            name = None
        offbi = 0

        offby = sum([x[5] for x in pktinfo[:pktinfo.index(parinfo)]]) // 8 + TM_HEADER_LEN  # +TM_HEADER_LEN for header
        # tmlist_filt = Tm_filter_st(tmlist, st, sst, apid, sid)[-last:] if tmfilter else tmlist[-last:]
        ufmt = ptt(ptc, pfc)

    else:
        userpar = json.loads(cfg[CFG_SECT_PLOT_PARAMETERS][param])
        st = int(userpar['ST'])
        sst = int(userpar['SST'])
        apid = int(userpar['APID'])
        sid = None if (('SID' not in userpar) or (userpar['SID'] is None)) else int(userpar['SID'])
        offby, ufmt = userpar['bytepos'], userpar['format']
        offbi = userpar['offbi'] if 'offbi' in userpar else 0
        descr, unit, name = param, None, None

    bylen = csize(ufmt)
    if isinstance(tmlist, list):
        tmlist_filt = Tm_filter_st(tmlist, st=st, sst=sst, apid=apid, sid=sid)[-last:] if tmfilter else tmlist[-last:]
    else:
        tmlist_filt = filter_rows(tmlist, st=st, sst=sst, apid=apid, sid=sid)[-last:] if tmfilter else tmlist[-last:]
        tmlist_filt = [x.raw for x in tmlist_filt]

    if name is not None:
        que = 'SELECT pcf.pcf_categ,pcf.pcf_curtx from pcf where pcf_name="%s"' % name
        dbres = dbcon.execute(que)
        fetch = dbres.fetchall()

        if not fetch:
            logger.error('Parameter {} not found in MIB.'.format(name))
            return

        categ, curtx = fetch[0]

        if mk_array:
            xy = [(get_cuctime(tm),
                   get_calibrated(name, read_stream(io.BytesIO(tm[offby:offby + bylen]), ufmt, offbi=offbi, none_on_fail=True),
                                  properties=[ptc, pfc, categ, curtx], numerical=numerical, nocal=True)) for tm in tmlist_filt]  # no calibration here, done below on array
        else:
            xy = [(get_cuctime(tm),
                   get_calibrated(name, read_stream(io.BytesIO(tm[offby:offby + bylen]), ufmt, offbi=offbi, none_on_fail=True),
                                  properties=[ptc, pfc, categ, curtx], numerical=numerical, nocal=nocal)) for tm in
                  tmlist_filt]

    else:
        xy = [(get_cuctime(tm), read_stream(io.BytesIO(tm[offby:offby + bylen]), ufmt, offbi=offbi, none_on_fail=True)) for tm in tmlist_filt]

    dbcon.close()

    if not mk_array:
        return xy, (descr, unit)

    try:
        arr = np.array(np.array(xy).T, dtype='float')

        # calibrate y values
        if not nocal and name is not None:
            get_cap_yval(name, arr[1, 0])  # calibrate one value to get name into _cap_cache

            if _cap_cache[name] is None:
                # try custom calibration if not in MIB
                if cal is not None:
                    arr[1, :] = cal.calibrate_ext(arr[1, :], pcf_name_to_descr(name))
                return arr, (descr, unit)

            xvals, yvals = _cap_cache[name]
            arr[1, :] = np.interp(arr[1, :], xvals, yvals, left=np.nan, right=np.nan)

        return arr, (descr, unit)

    except (ValueError, IndexError):
        return np.array(xy, dtype='float, U32'), (descr, unit)


def Hk_filter(tmlist, st, sst, apid=None, sid=None):
    """

    :param tmlist:
    :param st:
    :param sst:
    :param apid:
    :param sid:
    :return:
    """
    # if apid in (None, '') and sid not in (0, None):
    #     return [tm for tm in tmlist if (
    #             len(tm) > TM_HEADER_LEN and (tm[7], tm[8], tm[TM_HEADER_LEN]) == (st, sst, sid))]
    # elif sid not in (0, None):
    #     return [tm for tm in tmlist if (
    #             len(tm) > TM_HEADER_LEN and (tm[7], tm[8], struct.unpack('>H', tm[:2])[0] & 0b0000011111111111,
    #                                          tm[TM_HEADER_LEN]) == (st, sst, apid, sid))]
    return Tm_filter_st(tmlist, st=st, sst=sst, apid=apid, sid=sid)


def show_extracted_packet():
    """
    Get packet data selected in Pool Viewer

    :return:
    """
    pv = dbus_connection('poolviewer', communication['poolviewer'])
    if not pv:
        logger.warning('Could not obtain selected packets from PV!')
        return

    return eval(pv.Functions('selected_packet'))


def packet_selection():
    """
    Alias for show_extracted_packet call

    :return:
    """
    return show_extracted_packet()


def get_module_handle(module_name, instance=1, timeout=5):
    """
    Try getting the DBUS proxy object for the module_name module for timeout seconds.

    :param module_name:
    :param instance:
    :param timeout:
    :return:
    """
    if instance is None:
        instance = communication[module_name]

    module = None

    t1 = time.time()
    while (time.time() - t1) < timeout:
        try:
            # module = dbus.SessionBus().get_object(cfg.get('ccs-dbus_names', module_name) + str(instance), '/Messagelistner')
            module = dbus_connection(module_name, instance)
            if module:
                break
            else:
                time.sleep(.2)
        except dbus.DBusException as err:
            logger.info(err)
            module = False
            time.sleep(0.5)

    if module:
        return module
    else:
        try:
            # try one last time with fixed instance
            module = dbus_connection(module_name, instance=1)
            if not module:
                raise ValueError
            return module
        except Exception as err:
            logger.error('No running {} instance found'.format(module_name.upper()))
            return False


def _get_ccs_dbus_names(exclude=None):
    if exclude is None:
        exclude = []

    dbus_names = dbus.SessionBus().list_names()
    ccs_names = [cfg['ccs-dbus_names'][mod] for mod in cfg['ccs-dbus_names'] if mod not in exclude]
    ccs_modules = [mod for mod in dbus_names if mod.startswith(tuple(ccs_names))]

    return ccs_modules


def _quit_module(module_name, instance=1):
    mod = get_module_handle(module_name, instance=instance)

    if not mod:
        logger.error('{}{} not found on DBus').format(module_name, instance)
        return False

    try:
        mod.Functions('quit_func')
        return True
    except Exception as err:
        logger.exception(err)
        return False


def _close_modules():
    dbus_names = _get_ccs_dbus_names(exclude=['editor'])
    while dbus_names:
        print(dbus_names)
        for module in dbus_names:
            _, name, iid = module.split('.')
            success = _quit_module(name, int(iid.replace('communication', '')))
            if success:
                logger.info('Closed {}'.format(module))
            else:
                logger.error('Could not close {}'.format(module))

        dbus_names = _get_ccs_dbus_names(exclude=['editor'])

    logger.info('Closed all modules')


def connect(pool_name, host, port, protocol='PUS', is_server=False, timeout=10, delete_abandoned=False, try_delete=True,
            pckt_filter=None, options='', drop_rx=False, drop_tx=False):
    """
    Accessibility function for 'connect' in pus_datapool

    :param pool_name:
    :param host:
    :param port:
    :param return_socket:
    :param is_server:
    :param timeout:
    :param delete_abandoned:
    :param try_delete:
    :param pckt_filter:
    :param options:
    :param drop_rx:
    :param drop_tx:
    :param protocol:
    :return:
    """
    pmgr = get_module_handle('poolmanager')

    if not pmgr:
        return

    kwarguments = str({'protocol': protocol,
                       'is_server': is_server,
                       'timeout': timeout,
                       'delete_abandoned': delete_abandoned,
                       'try_delete': try_delete,
                       'pckt_filter': pckt_filter,
                       'options': options,
                       'drop_rx': drop_rx,
                       'drop_tx': drop_tx})

    # kwarguments = {'return_socket': return_socket, 'is_server': is_server, 'timeout': timeout,
    #                'delete_abandoned': delete_abandoned, 'try_delete': try_delete, 'pckt_filter': pckt_filter,
    #                'options': options, 'drop_rx': drop_rx, 'drop_tx': drop_tx, 'protocol': protocol}

    pmgr.Functions('connect', pool_name, host, port, {'kwargs': dbus.Dictionary({'options': kwarguments,
                                                                                 'override_with_options': '1'})})


def connect_tc(pool_name, host, port, protocol='PUS', drop_rx=True, timeout=10, is_server=False, use_socket=None,
               options=''):
    """
    Accessibility function for 'connect_tc' in pus_datapool

    :param pool_name:
    :param host:
    :param port:
    :param drop_rx:
    :param protocol:
    :param timeout:
    :param is_server:
    :param use_socket:
    :param options:
    :return:
    """
    pmgr = get_module_handle('poolmanager')

    if not pmgr:
        return

    kwarguments = str({'protocol': protocol,
                       'is_server': is_server,
                       'timeout': timeout,
                       'options': options,
                       'drop_rx': drop_rx,
                       'use_socket': use_socket})

    pmgr.Functions('connect_tc', pool_name, host, port, {'kwargs': dbus.Dictionary({'options': kwarguments,
                                                                                    'override_with_options': '1'})})


##
#  TC send (DB)
#
#  @param cmd       CCF_DESCR string of the TC to be issued
#  @param args      Parameters required by the TC specified with _cmd_
#  @param ack       Override the I-DB TC acknowledment value (4-bit binary string, e.g., '0b1011')
#  @param pool_name Name of pool bound to socket connected to the C&C port
#  @param sleep     Idle time in seconds after the packet has been sent. Useful if function is called repeatedly in a
#  loop to prevent too many packets are being sent over the socket in a too short time interval.
def Tcsend_DB(cmd, *args, ack=None, pool_name=None, sleep=0., no_check=False, pkt_time=False, **kwargs):
    """
    Build and send a TC packet whose structure is defined in the MIB. Note that for repeating parameter groups
    the arguments are interleaved, e.g., ParID1, ParVal1, ParID2, ParVal2,... Use the function *interleave_lists*
    to create a list ordered that way.

    :param cmd: command name as specified in *CCF_DESCR*
    :type cmd: str
    :param args: unpacked list of (calibrated) TC parameter values, order is as specified in the MIB
    :param ack: override acknowledge flags in PUS header
    :type ack: int
    :param pool_name:
    :param sleep:
    :param no_check:
    :param pkt_time:
    :param kwargs:
    :return:
    """
    t1 = time.time()

    pmgr = dbus_connection('poolmanager', communication['poolmanager'])
    if not pmgr:
        return

    try:
        tc, (st, sst, apid) = Tcbuild(cmd, *args, ack=ack, no_check=no_check, **kwargs)
    except TypeError as e:
        raise e

    if pool_name is None:
        pool_name = pmgr.Variables('tc_name')

    sent = _tcsend_common(tc, apid, st, sst, pool_name=pool_name, pkt_time=pkt_time)

    dt = time.time() - t1
    time.sleep(max(sleep - dt, 0))

    return sent


##
#  Generate TC
def Tcbuild(cmd, *args, sdid=0, ack=None, no_check=False, hack_value=None, source_data_only=False, **kwargs):
    """
    Create TC bytestring for CMD with corresponding parameters

    :param cmd: CCF_DESCR string of the requested TC
    :param args: Parameters required by the cmd
    :param sdid:
    :param ack: Override the I-DB TC acknowledment value (4-bit binary, e.g., 0b1011)
    :param no_check:
    :param hack_value:
    :param source_data_only:
    :param kwargs:
    :return:
    """
    # with self.poolmgr.lock:
    # que = 'SELECT ccf_type,ccf_stype,ccf_apid,ccf_npars,cdf.cdf_grpsize,cdf.cdf_eltype,cdf.cdf_ellen,' \
    #       'cdf.cdf_value,cpc.cpc_ptc,cpc.cpc_pfc,cpc.cpc_descr,cpc.cpc_pname FROM ccf LEFT JOIN cdf ON ' \
    #       'cdf.cdf_cname=ccf.ccf_cname LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname ' \
    #       'WHERE BINARY ccf_descr="%s"' % cmd
    # dbcon = scoped_session_idb
    # params = dbcon.execute(que).fetchall()
    # dbcon.close()

    try:
        params = _get_tc_params(cmd)
    except SQLOperationalError:
        scoped_session_idb.close()
        params = _get_tc_params(cmd)

    try:
        st, sst, apid, npars = params[0][:4]
    except IndexError:
        # print('Unknown command "{}"'.format(cmd))
        # Notify.Notification.new('Unknown command "{}"'.format(cmd)).show()
        raise NameError('Unknown command "{}"'.format(cmd))

    if ack is None:
        ack = bin(Tcack(cmd))

    if npars == 0:
        pdata = b''

        if source_data_only:
            return pdata

    else:
        # check for padded parameters
        padded, = np.where(np.array([i[5] for i in params]) == 'A')
        if len(padded) != 0:
            for n in padded:
                x = list(params[n])
                x[-4:-2] = 'SPARE', x[-6]
                params.remove(params[n])
                params.insert(n, tuple(x))

        if np.any([i[4] for i in params]):
            varpos, = np.where([i[4] for i in params])
            grpsize = params[varpos[0]][4]
            # are there any spares/fixed before the rep. counter? TODO: nested/multiple repetition counters?
            pars_noedit = [p for p in params[:varpos[0]] if p[5] in ('A', 'F')]
            npars_noedit = len(pars_noedit)
            repfac = int(args[varpos[0] - npars_noedit])

            fix = encode_pus(params[:varpos[0] + 1], *[tc_param_alias(p[-1], v, no_check=no_check) for p, v in
                         zip_no_pad(params[:varpos[0] + 1], args[:varpos[0] - npars_noedit + 1])])

            if not [i[8] for i in params].count(11):
                var = encode_pus(repfac * params[varpos[0] + 1:varpos[0] + 1 + grpsize], *[tc_param_alias(p[-1], v, no_check=no_check) for p, v in
                                                    zip_no_pad(repfac * params[varpos[0] + 1:varpos[0] + 1 + grpsize],
                                                    args[varpos[0] - npars_noedit + 1:varpos[0] - npars_noedit + 1 + grpsize * repfac])])

            # for derived type parameters, not supported for SMILE
            else:
                raise NotImplementedError("Deduced parameter types in TCs are not supported!")
                # formats, args2 = build_packstr_11(st, sst, apid, params, varpos[0], grpsize, repfac, *args,
                #                                        no_check=no_check)
                # #var = pack(fstring, *args2[varpos[0] + 1:varpos[0] + 1 + grpsize * repfac])
                # var = encode_pus(formats, *args2[varpos[0] + 1:varpos[0] + 1 + grpsize * repfac])

            # add the parameters after the variable part, if any
            npars_with_var = varpos[0] + grpsize + 1
            if len(params) > npars_with_var:
                fix2 = encode_pus(params[npars_with_var:],
                                  *[tc_param_alias(p[-1], v, no_check=no_check) for p, v in
                                    zip_no_pad(params[npars_with_var:],
                                               args[npars_with_var - npars_noedit + grpsize * (repfac - 1):])])
            else:
                fix2 = b''

            pdata = fix + var + fix2

            if source_data_only:
                return pdata

        else:
            if hack_value is None:
                values = [tc_param_alias(p[-1], v, no_check=no_check) for p, v in zip_no_pad(params, args)]
            else:
                values = hack_value

            pdata = encode_pus(params, *values)

            if source_data_only:
                return pdata

    return Tcpack(st=st, sst=sst, apid=int(apid), data=pdata, sdid=sdid, ack=ack, **kwargs), (st, sst, apid)


def _get_tc_params(cmd, paf_cal=False):

    if paf_cal:
        que = 'SELECT ccf_type,ccf_stype,ccf_apid,ccf_npars,cdf.cdf_grpsize,cdf.cdf_eltype,cdf.cdf_ellen,' \
              'cdf.cdf_value,cpc.cpc_ptc,cpc.cpc_pfc,cpc.cpc_descr,cpc.cpc_pname,cpc.cpc_pafref FROM ccf LEFT JOIN cdf ON ' \
              'cdf.cdf_cname=ccf.ccf_cname LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname ' \
              'WHERE BINARY ccf_descr="%s"' % cmd
    else:
        que = 'SELECT ccf_type,ccf_stype,ccf_apid,ccf_npars,cdf.cdf_grpsize,cdf.cdf_eltype,cdf.cdf_ellen,' \
              'cdf.cdf_value,cpc.cpc_ptc,cpc.cpc_pfc,cpc.cpc_descr,cpc.cpc_pname FROM ccf LEFT JOIN cdf ON ' \
              'cdf.cdf_cname=ccf.ccf_cname LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname ' \
              'WHERE BINARY ccf_descr="%s"' % cmd

    params = scoped_session_idb.execute(que).fetchall()
    scoped_session_idb.close()
    return params


def encode_pus(params, *values, params_as_fmt_string=False):
    """

    :param params:
    :param values:
    :param params_as_fmt_string:
    :return:
    """
    if params_as_fmt_string or isinstance(params, str):
        return struct.pack(params, *values)

    if not isinstance(values, list):
        values = list(values)

    ed_pars = [param for param in params if param[5] not in ['A', 'F']]
    if len(ed_pars) != len(values):
        raise ValueError('Wrong number of parameters: Expected {}, but got {}.\n{}'.format(len(ed_pars), len(values), ', '.join(x[10] for x in ed_pars)))

    params_nospares = [param for param in params if param[5] not in ['A']]

    # insert fixed parameter values, cdf_value=param[7]
    for i, par in enumerate(params_nospares):
        if par[5] == 'F':
            fixed_val = cast_str_value_ptc(par[7], par[8])
            values.insert(i, tc_param_alias(par[-1], fixed_val))

    fmts = [parameter_ptt_type_tc(par) for par in params]

    # deduced parameter types are not supported for TCs TODO
    if 'deduced' in fmts:
        raise NotImplementedError("Deduced parameter types in TCs are not supported! ({})".format(', '.join([p[-2] for p in params if p[8] == 11])))

    try:
        fmt_string = '>'+''.join(fmts)
        return struct.pack(fmt_string, *values)

    except struct.error as err:
        logger.debug(err)
        # proper insertion of spares
        vals_iter = iter(values)
        return b''.join([pack_bytes(fmt, next(vals_iter)) if not fmt.endswith('x') else struct.pack(fmt) for fmt in fmts])


def cast_str_value_ptc(val, ptc):
    """
    Cast string type value to type given by PTC

    :param val:
    :param ptc:
    :return:
    """

    if ptc == 1:
        return int(bool(int(val)))
    elif ptc == 2:
        try:
            v = int(val)  # test if val is text-calibrated
            logger.info("Numerical fixed value ({}) defined for enumerated type parameter (PTC=2).".format(val))
            return v
        except ValueError:
            return str(val)
    elif ptc in [3, 4]:
        try:
            return int(val)  # test if val is text-calibrated
        except ValueError:
            logger.info("String fixed value ({}) defined for integer type parameter (PTC=3).".format(val))
            return val
    elif ptc in [5, 9, 10]:
        return float(val)
    elif ptc == 7:
        return bytes.fromhex(val)
    elif ptc == 8:
        return str(val)
    else:
        raise NotImplementedError("TC fixed parameter values not supported for PTC={}".format(ptc))


def pack_bytes(fmt, value, bitbuffer=0, offbit=0):
    """

    :param fmt:
    :param value:
    :param bitbuffer:
    :param offbit:
    :return:
    """
    if fmt == 'I24':
        x = value.to_bytes(3, 'big')

    elif fmt == 'i24':
        x = value.to_bytes(3, 'big', signed=True)

    elif fmt.startswith('uint'):
        bitlen = int(fmt[4:])
        bitsize = (bitlen // 8 + 1) * 8
        shifted = (value << (bitsize - bitlen - offbit)) + bitbuffer
        if (bitsize - bitlen - offbit) == 0:
            x = shifted.to_bytes(bitsize // 8, 'big')
        else:
            return shifted

    elif fmt.startswith('oct'):
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError('Value packed with fmt "{}" is not an octet string: {} {}!'.format(fmt, value, type(value)))
        if len(value) != int(fmt[3:]):
            logger.warning('Length of octet string ({}) does not match format {}!'.format(len(value), fmt))
        x = struct.pack('>{}s'.format(fmt[3:]), value)

    elif fmt.startswith('ascii'):
        if not isinstance(value, str):
            raise TypeError('Value packed with fmt "{}" is not a string: {} {}!'.format(fmt, value, type(value)))
        if len(value) != int(fmt[5:]):
            logger.warning('Length of string ({}) does not match format {}!'.format(len(value), fmt))
        x = struct.pack('>{}s'.format(fmt[5:]), value.encode(encoding='ascii'))

    elif fmt == timepack[0]:
        x = calc_timestamp(value, sync=None, return_bytes=True)

    elif value is None:
        x = struct.pack('>' + fmt)

    else:
        x = struct.pack('>' + fmt, value)

    return x


def date_to_cuc_bytes(date, sync=None):
    """
    Create CUC time bytes from date string.

    :param date: date as ISO formatted string
    :param sync: CUC sync flag, if None sync byte is omitted
    """
    if sync in [1, True]:
        sync = 'S'
    elif sync in [0, False]:
        sync = 'U'

    date = duparser.parse(date)

    if date.utcoffset() is None:
        date = date.replace(tzinfo=datetime.timezone.utc)

    float_time = utc_to_cuc(date)
    return calc_timestamp(float_time, sync=sync, return_bytes=True)


##
# parameter_ptt_type
#
# Returns the format of the input bytes for TC (list has to be formated the correct way)
# @param parameters Input List of one parameter
def parameter_ptt_type_tc(par):
    """

    :param par:
    :return:
    """
    return ptt(par[-4], par[-3])


##
#  Acknowledgement
#
#  Get type acknowledgement type for give service (sub-)type and APID from I-DB
#  @param st   Service type
#  @param sst  Service sub-type
#  @param apid APID of TC
def Tcack(cmd):
    """
    Get type acknowledgement type for give service (sub-)type and APID from I-DB

    :param cmd:
    :return:
    """
    que = 'SELECT ccf_ack FROM ccf WHERE BINARY ccf_descr="{}"'.format(cmd)
    dbcon = scoped_session_idb
    ack = int(dbcon.execute(que).fetchall()[0][0])
    dbcon.close()
    return ack

##
#  Parameter alias
#
#  Numerical/textual calibration and range check for value val of parameter param
#  @param param CPC_PNAME
#  @param val   Parameter value
def tc_param_alias(param, val, no_check=False):
    """
    Numerical/textual calibration and range check for value val of parameter param

    :param param:
    :param val:
    :param no_check:
    :return:
    """
    que = 'SELECT cpc_prfref,cpc_ccaref,cpc_pafref,cpc_descr,cpc_categ from cpc where cpc_pname="%s"' % param
    dbcon = scoped_session_idb
    prf, cca, paf, pdesc, categ = dbcon.execute(que).fetchall()[0]
    # this is a workaround for datapool items not being present in PAF/PAS table # DEPRECATED!
    # if param in ['DPP70004', 'DPP70043']:  # DataItemID in TC(211,1)
    #     val = get_pid(val)
    # else:
    #     pass

    # check if parameter holds a data pool ID (categ=P) and look up numerical value in case it is given as string
    if categ == 'P' and isinstance(val, str):
        try:
            val = DP_ITEMS_TO_IDS[val]
        except KeyError:
            raise KeyError('Unknown data pool item "{}"'.format(val))

    if (not no_check) and (prf is not None):
        in_range, error = tc_param_in_range(prf, val, pdesc)
        if not in_range:
            raise ValueError('Range check failed\n{}'.format(error))
        else:
            # subtract offset from PID to be compatible with IASW (CHEOPS only)
            if categ == 'P':
                val -= pid_offset
    else:
        if categ == 'P':
            val -= pid_offset

    if paf is not None:

        que = 'SELECT pas_alval from pas where pas_numbr="%s" and pas_altxt="%s"' % (paf, val)
        dbres = dbcon.execute(que)
        try:
            alval, = dbres.fetchall()[0]
        except IndexError as error:
            if no_check:
                alval = val
                logger.info('Inserting unchecked value for {}: {}'.format(pdesc, val))
            else:
                que = 'SELECT pas_altxt from pas where pas_numbr="%s"' % paf
                alvals = [x[0] for x in dbcon.execute(que).fetchall()]
                raise ValueError('Invalid {} value: {}. Allowed values are: {}.'.format(pdesc, val, ', '.join(alvals)))
        finally:
            dbcon.close()

        return int(alval)
    elif cca is not None:

        que = 'SELECT ccs_xvals,ccs_yvals from ccs where ccs_numbr="%s"' % cca
        dbres = dbcon.execute(que)
        xvals, yvals = np.array([x for x in zip(*dbres.fetchall())], dtype=float)
        dbcon.close()
        alval = int(np.interp(val, xvals, yvals))

        return alval
    else:

        dbcon.close()

        return val


##
#  Get PID
#  Translates name of data pool variable to corresponding ID, based on DP_ITEMS_TO_IDS look-up table
#  @param paramname Name of the data pool variables
def get_pid(parnames):
    """

    :param parnames:
    :return:
    """
    # if isinstance(parnames, int):
    #     return parnames
    if isinstance(parnames, str):
        parnames = [parnames]

    # if len(set(parnames)) != len(parnames):
    #     msg = "Duplicate parameters will be ignored! {}".format(set([p for p in parnames if parnames.count(p) > 1]))
    #     logger.warning(msg)

    pids = [DP_ITEMS_TO_IDS[parname] for parname in parnames]

    return pids if len(pids) > 1 else pids[0]


def get_sid(st, sst, apid):
    """

    :param st:
    :param sst:
    :param apid:
    :return:
    """
    if (st, sst, apid) in SID_LUT:
        return SID_LUT[(st, sst, apid)]
    else:
        try:
            logger.warning('APID {} not known'.format(apid))
            return SID_LUT[(st, sst, None)]
        except KeyError:
            return


##
#  Parameter range check
#
#  Check if parameter is within specified range
#  @param prf   PRV_NUMBR
#  @param val   Parameter value
#  @param pdesc Parameter DESCR
def tc_param_in_range(prf, val, pdesc):
    """

    :param prf:
    :param val:
    :param pdesc:
    :return:
    """
    que = 'SELECT prf_dspfmt,prf_radix,prv_minval,prv_maxval FROM prv INNER JOIN prf ON prf_numbr=prv_numbr WHERE prv_numbr="{}"'.format(prf)
    dbcon = scoped_session_idb
    prfs = dbcon.execute(que).fetchall()
    dbcon.close()
    if prfs[0][0] in ['I', 'U', 'R']:  # numerical range check if not text encoded (A) parameter
        if prfs[0][1] == 'D':
            ranges = [(int(pval[2], 10), int(pval[3], 10)) for pval in prfs]
        elif prfs[0][1] == 'H':
            ranges = [(int(pval[2], 16), int(pval[3], 16)) for pval in prfs]
        if not any([rng[0] <= float(val) <= rng[1] for rng in ranges]):
            limits = ' | '.join(['{:}-{:}'.format(*rng) for rng in ranges])
            # print('Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits))
            logger.warning('Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits))
            # Notify.Notification.new('Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits)).show()
            return False, 'Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits)
    elif prfs[0][0] == 'A':
        if val not in [i[2] for i in prfs]:
            valid = ' | '.join([i[2] for i in prfs])
            # print('Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid))
            logger.warning('Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid))
            # Notify.Notification.new('Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid)).show()
            return False, 'Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid)
    else:
        logger.warning('Range check for parameter type "{}" not implemented [{}]'.format(prfs[0][0], pdesc))  # TODO: no check for time ranges yet
    return True, ''


##
#  ZIPnoPAD
#
#  Zip parameter-value pairs, skipping padding parameters
#  @param params List of TC parameter properties
#  @param args   List of supplied parameter values
def zip_no_pad(params, args):
    """

    :param params:
    :param args:
    :return:
    """
    # [params.pop(i) for i, j in enumerate(params) if j[-4] in ['SPARE', 'PAD']]
    params = [param for param in params if param[5] not in ['A', 'F']]
    return zip(params, args)


##
#  Generate PUS packet
#
#  Create TC packet conforming to PUS
#  @param version version number
#  @param typ     packet type (TC/TM)
#  @param dhead   data field header flag
#  @param apid    application data ID
#  @param gflags  sequence flags
#  @param sc      sequence count
#  @param pktl    packet length
#  @param tmv     PUS version
#  @param ack     acknowledgement flags
#  @param st      service type
#  @param sst     service sub-type
#  @param destid  source/destination ID
#  @param data    application data
def Tmpack(data=b'', apid=321, st=1, sst=1, destid=0, version=0, typ=0, timestamp=0, dhead=1, gflags=0b11,
           sc=None, tmv=PUS_VERSION, tref_stat=0, msg_type_cnt=0, pktl=None, chksm=None, **kwargs):
    """
    Create TM packet conforming to PUS

    :param data:
    :param apid:
    :param st:
    :param sst:
    :param destid:
    :param version:
    :param typ:
    :param timestamp:
    :param dhead:
    :param gflags:
    :param sc:
    :param tmv:
    :param tref_stat:
    :param msg_type_cnt:
    :param pktl:
    :param chksm:
    :param kwargs:
    :return:
    """
    if pktl is None:
        # pktl = len(data) * 8 + (TC_HEADER_LEN + PEC_LEN - 7)  # 7=-1(convention)+6(datahead)+2(CRC) # len(data) *8, data in bytes has to be bits
        pktl = len(data) + (TM_HEADER_LEN + PEC_LEN - 7)

    if sc is None:
        sc = counters.setdefault(int(str(apid), 0), 1) % 2 ** 14  # wrap around counter to fit in 14 bits
        if sc == 0:
            sc += 1
            counters[int(str(apid))] += 1  # 0 is not allowed for seq cnt

    tm = PUSpack(version=version, typ=typ, dhead=dhead, apid=apid, gflags=gflags, sc=sc, pktl=pktl,
                 tmv=tmv, st=st, sst=sst, sdid=destid, timestamp=timestamp, tref_stat=tref_stat,
                 msg_type_cnt=msg_type_cnt, data=data, **kwargs)

    if chksm is None:
        chksm = crc(tm)
    tm += struct.pack('>H', chksm)

    return tm


##
#  Generate PUS packet
#
#  Create TC packet conforming to PUS
#  @param version version number
#  @param typ     packet type (TC/TM)
#  @param dhead   data field header flag
#  @param apid    application data ID
#  @param gflags  sequence flags
#  @param sc      sequence count
#  @param pktl    packet length
#  @param tmv     PUS version
#  @param ack     acknowledgement flags
#  @param st      service type
#  @param sst     service sub-type
#  @param sdid    source/destination ID
#  @param data    application data
def Tcpack(data=b'', apid=0x14c, st=1, sst=1, sdid=0, version=0, typ=1, dhead=1, gflags=0b11, sc=None,
           tmv=PUS_VERSION, ack=0b1001, pktl=None, chksm=None, **kwargs):
    """
    Create TC packet conforming to PUS

    :param data:
    :param apid:
    :param st:
    :param sst:
    :param sdid:
    :param version:
    :param typ:
    :param dhead:
    :param gflags:
    :param sc:
    :param tmv:
    :param ack:
    :param pktl:
    :param chksm:
    :param kwargs:
    :return:
    """
    if pktl is None:
        pktl = len(data) + (TC_HEADER_LEN + PEC_LEN - 7)  # 7=-1(convention)+6(datahead)+2(CRC)

    if sc is None:
        sc = counters.setdefault(int(str(apid), 0), 1) % 2 ** 14  # wrap around counter to fit in 14 bits
        if sc == 0:
            sc += 1
            counters[int(str(apid))] += 1  # 0 is not allowed for seq cnt
    tc = PUSpack(version=version, typ=typ, dhead=dhead, apid=int(str(apid), 0), gflags=int(str(gflags), 0),
                 sc=sc, pktl=pktl, tmv=tmv, ack=int(str(ack), 0), st=st, sst=sst, sdid=sdid, data=data, **kwargs)

    if chksm is None:
        chksm = crc(tc)

    tc += chksm.to_bytes(2, 'big')  # 16 bit CRC

    return tc


##
#  Generate PUS packet
#
#  @param version version number
#  @param typ     packet type (TC/TM)
#  @param dhead   data field header flag
#  @param apid    application data ID
#  @param gflags  sequence flags
#  @param sc      sequence count
#  @param pktl    packet length
#  @param tmv     PUS version
#  @param ack     acknowledgement flags
#  @param st      service type
#  @param sst     service sub-type
#  @param sdid    source/destination ID
#  @param data    application data
def PUSpack(version=0, typ=0, dhead=0, apid=0, gflags=0b11, sc=0, pktl=0,
            tmv=PUS_VERSION, ack=0, st=0, sst=0, sdid=0, tref_stat=0, msg_type_cnt=0, timestamp=0, data=b'', **kwargs):
    """
    Create bytestring conforming to PUS with no CRC appended, for details see PUS documentation

    :param version:
    :param typ:
    :param dhead:
    :param apid:
    :param gflags:
    :param sc:
    :param pktl:
    :param tmv:
    :param ack:
    :param st:
    :param sst:
    :param sdid:
    :param tref_stat:
    :param msg_type_cnt:
    :param timestamp:
    :param data:
    :param kwargs:
    :return:
    """
    if typ == 1 and dhead == 1:
        header = TCHeader()
    elif typ == 0 and dhead == 1:
        header = TMHeader()
    else:
        header = PHeader()

    header.bits.PKT_VERS_NUM = version
    header.bits.PKT_TYPE = typ
    header.bits.SEC_HEAD_FLAG = dhead
    header.bits.APID = apid
    header.bits.SEQ_FLAGS = gflags
    header.bits.PKT_SEQ_CNT = sc
    header.bits.PKT_LEN = pktl

    # PUS-A
    if PUS_VERSION == 1:
        if typ == 1 and dhead == 1:
            header.bits.CCSDS_SEC_HEAD_FLAG = 0
            header.bits.PUS_VERSION = tmv
            header.bits.ACK = ack
            header.bits.SERV_TYPE = st
            header.bits.SERV_SUB_TYPE = sst
            header.bits.SOURCE_ID = sdid

        elif typ == 0 and dhead == 1:
            header.bits.SPARE1 = 0
            header.bits.PUS_VERSION = tmv
            header.bits.SPARE2 = 0
            header.bits.SERV_TYPE = st
            header.bits.SERV_SUB_TYPE = sst
            header.bits.DEST_ID = sdid
            ctime, ftime, sync = calc_timestamp(timestamp)
            sync = 0 if sync is None else sync
            header.bits.CTIME = ctime
            header.bits.FTIME = ftime
            header.bits.TIMESYNC = sync
            # header.bits.SPARE = 0

    # PUS-C
    elif PUS_VERSION == 2:
        if typ == 1 and dhead == 1:
            header.bits.PUS_VERSION = tmv
            header.bits.ACK = ack
            header.bits.SERV_TYPE = st
            header.bits.SERV_SUB_TYPE = sst
            header.bits.SOURCE_ID = sdid

        elif typ == 0 and dhead == 1:
            header.bits.PUS_VERSION = tmv
            # header.bits.SC_REFTIME = tref_stat  # replaced with TIMESYNC to be backwards-compatible with PUS-A
            header.bits.SERV_TYPE = st
            header.bits.SERV_SUB_TYPE = sst
            header.bits.MSG_TYPE_CNT = msg_type_cnt
            header.bits.DEST_ID = sdid
            ctime, ftime, sync = calc_timestamp(timestamp)
            sync = 0 if sync is None else sync
            header.bits.CTIME = ctime
            header.bits.FTIME = ftime
            header.bits.TIMESYNC = sync

    else:
        raise NotImplementedError('Invalid PUS version: {}'.format(PUS_VERSION))

    return bytes(header.bin) + data


##
#  Build Packstring 11
#
#  Create pack string if datatypes are defined in the packet iti.e. PTC/PTF=11/0
#  @param st      Service type
#  @param sst     Service sub-tpye
#  @param apid    APID of TC
#  @param params  List of parameter properties
#  @param varpos  Position of the parameter indicating repetition
#  @param grpsize Parameter group size
#  @param repfac  Number of parameter (group) repetitions
def build_packstr_11(st, sst, apid, params, varpos, grpsize, repfac, *args, no_check=False):
    """

    :param st:
    :param sst:
    :param apid:
    :param params:
    :param varpos:
    :param grpsize:
    :param repfac:
    :param args:
    :param no_check:
    :return:
    """
    ptypeindex = [i[-1] == FMT_TYPE_PARAM for i in params].index(True)  # check where fmt type defining parameter is
    ptype = args[varpos + ptypeindex::grpsize]
    args2 = list(args)
    args2[varpos + 1:] = [tc_param_alias(param[-1], val, no_check=no_check) for param, val in
                          zip(params[varpos + 1:] * repfac, args[varpos + 1:])]
    ptc = 0
    varlist = []
    for par in params[varpos + 1:] * repfac:
        if par[-4] != 11:
            #varlist.append(ptt[par[-4]][par[-3]])
            varlist.append(parameter_ptt_type_tc(par))
        else:
            varlist.append(
                ptt(par[-4], par[-3])[tc_param_alias(FMT_TYPE_PARAM, ptype[ptc], no_check=no_check)])
            #varlist.append(ptt[par[-4]][par[-3]][tc_param_alias('DPP70044', ptype[ptc], no_check=no_check)])
            ptc += 1
    return varlist, args2


##
# TC send (common part of Tcsend_DB and Tcsend)
#
#  @param tc_bytes  TC as byte array to send
#  @param apid      APID of the TC, as hex-string
#  @param st        Service type of TC
#  @param sst       Service sub-type of TC
#  @param sleep     Idle time in seconds after the packet has been sent. Useful if function is called repeatedly in a loop to prevent too many packets are being sent over the socket in a too short time interval.
#  @param pool_name Name of pool bound to socket connected to the C&C port
def _tcsend_common(tc_bytes, apid, st, sst, sleep=0., pool_name='LIVE', pkt_time=False):

    global counters

    # Note: in general, it is not possible to obtain the OBC time, thus the last packet time is used if available
    if pkt_time:
        t = get_last_pckt_time(pool_name=pool_name, string=False)
        if t is None:
            t = 0
    # Alternatively, use local time (JD)
    else:
        t = time.time()

    sent = Tcsend_bytes(tc_bytes, pool_name)
    if not sent:
        return

    # get the SSC of the sent packet
    ssc = counters.setdefault(int(str(apid), 0), 1)
    # increase the SSC counter
    counters[int(str(apid), 0)] += 1
    # More specific Logging format that is compatible with the TST
    log_dict = dict([('st', st),('sst', sst),('ssc', ssc),('apid', apid),('timestamp', t)])
    json_string = '{} {}'.format('#SENT TC', json.dumps(log_dict))
    logger.debug(json_string)
    # time.sleep(sleep)
    return apid, ssc, t


# get the CUC timestamp of the lastest TM packet
#   @param pool_name: name of the pool
#   @param string: <boolean> if true the CUC timestamp is returned as a string, otherwise as a float
#   @return: <CUC> timestamp or None if failing
def get_last_pckt_time(pool_name='LIVE', string=True, use_pmgr=False):
    """

    :param pool_name:
    :param string:
    :return:
    """

    if use_pmgr:
        pmgr = dbus_connection('poolmanager', communication['poolmanager'])

        if not pmgr:
            logger.warning('Accessing PMGR failed!')
            return

        packet = None
        # fetch the pool_name
        try:
            poolname = pmgr.Dictionaries('loaded_pools', pool_name)
        except (dbus.DBusException, KeyError):
            logger.error('Pool {} is not connected/accessible!'.format(pool_name))
            return

        filename = poolname[2]  # 3rd entry is the filename of the named tuple, named tuple not possible via dbus
        if not filename:
            filename = pool_name
    else:
        filename = pool_name

    # get the first packet from the pool
    dbcon = scoped_session_storage
    row = dbcon.query(
        DbTelemetry
    ).join(
        DbTelemetryPool,
        DbTelemetry.pool_id == DbTelemetryPool.iid
    ).filter(
        DbTelemetryPool.pool_name == filename, DbTelemetry.is_tm == 0
    ).order_by(
        DbTelemetry.idx.desc()
    ).first()
    dbcon.close()
    if row is not None:
        packet = row.raw
    else:
        logger.warning('get_packet_from_pool: failed to get packets from query')

    # extract the CUC timestamp
    if string:
        if packet is None:
            cuc = ''
        else:
            cuc = mkcucstring(packet)
    else:
        if packet is None:
            cuc = None
        else:
            try:
                cuc = get_cuctime(packet)
            except:
                logger.error(
                    'This TM packet does not have valid CUC timestamp fields:\n\t\tHeader: {}\n\t\tData: {}'
                    .format(Tmread(packet), Tmdata(packet)))
                cuc = None
    return cuc


def get_last_tc(pool_name, idbytes=False):
    dbcon = scoped_session_storage
    row = dbcon.query(
        DbTelemetry
    ).join(
        DbTelemetryPool,
        DbTelemetry.pool_id == DbTelemetryPool.iid
    ).filter(
        DbTelemetryPool.pool_name == pool_name, DbTelemetry.is_tm == 1
    ).order_by(
        DbTelemetry.idx.desc()
    ).first()
    dbcon.close()

    if idbytes:
        return row.raw[:4]  # return first 4 header bytes used for identification in PUS Ack service
    else:
        return row


def _has_tc_connection(pool_name, pmgr_handle):
    try:
        if not pmgr_handle.Functions('_is_tc_connection_active', pool_name):
            logger.error('"{}" is not connected to any TC socket!'.format(pool_name))
            return False
        else:
            return True
    except Exception as err:
        logger.error(err)
        return False


def _get_pmgr_handle(tc_pool=None):
    pmgr = dbus_connection('poolmanager', communication['poolmanager'])

    if not pmgr:
        return False

    # check if pool is connected
    if tc_pool is not None and not _has_tc_connection(tc_pool, pmgr):
        return False

    return pmgr


def Tcsend_bytes(tc_bytes, pool_name='LIVE', pmgr_handle=None):
    """

    :param tc_bytes:
    :param pool_name:
    :param pmgr_handle:
    :return:
    """
    if not pmgr_handle:
        pmgr = _get_pmgr_handle(pool_name)
    else:
        pmgr = pmgr_handle

    # Tell dbus with signature = that you send a byte array (ay), otherwise does not allow null bytes
    try:
        pmgr.Functions('tc_send', pool_name, tc_bytes, signature='ssay')
        return True
    except (dbus.DBusException, AttributeError):
        logger.error('Failed to send packet of length {} to {}!'.format(len(tc_bytes), pool_name))
        return False
    # logger.debug(msg)
    # pmgr.Functions('tc_send', pool_name, tc_bytes, ignore_reply=True)


##
#  Send C&C command
#
#  Send command to C&C socket
#  @param pool_name Name of the pool bound to the socket for CnC/TC communication
#  @param cmd         Command string to be sent to C&C socket
def CnCsend(cmd, pool_name=None, apid=1804):
    """

    :param cmd:
    :param pool_name:
    :param apid:
    :return:
    """
    global counters  # One can only Change variable as global since we are static
    # pmgr = dbus_connection('poolmanager', communication['poolmanager'])
    pmgr = get_module_handle('poolmanager')
    if pool_name is None:
        pool_name = pmgr.Variables('tc_name')

    pid = (apid >> 4) & 0x7F
    cat = apid & 0xF
    packed_data = CnCpack(data=cmd, pid=pid, cat=cat, sc=counters.setdefault(apid, 1))

    received = pmgr.Functions('socket_send_packed_data', packed_data, pool_name, signature='says')
    logger.info('[CNC sent:]' + str(packed_data))

    try:
        msg = bytes(received)
    except TypeError as err:
        logger.error(err)
        return

    if msg:
        counters[apid] += 1
        try:
            msg = msg.decode('ascii', errors='replace')
        except Exception as err:
            logger.error(err)
            return

        logger.info('[CNC response:] ' + msg)
        return msg


##
#  Generate CnC packet
#
#  Create packet conforming to C&C definition
#  @param data    Application data, as ASCII string
#  @param version Version number ('011' binary)
#  @param typ     Packet type, 0=TM, 1=TC
#  @param dhead   Data field header flag. C&C has no DFH (=0)
#  @param pid     Application PID
#  @param cat     Category
#  @param gflags  Segmentation flags
#  @param sc      Sequence counter
def CnCpack(data=b'', version=0b011, typ=1, dhead=0, pid=112, cat=12, gflags=0b11, sc=0):
    """

    :param data:
    :param version:
    :param typ:
    :param dhead:
    :param pid:
    :param cat:
    :param gflags:
    :param sc:
    :return:
    """
    if isinstance(data, str):
        data = data.encode('ascii')

    header = PHeader()
    header.bits.PKT_VERS_NUM = version
    header.bits.PKT_TYPE = typ
    header.bits.SEC_HEAD_FLAG = dhead
    header.bits.APID = (pid << 4) + cat
    header.bits.SEQ_FLAGS = gflags
    header.bits.PKT_SEQ_CNT = sc
    header.bits.PKT_LEN = len(data) - 1

    return bytes(header.bin) + data


##
#  Send data to socket
#
#  Send bytestring to specified socket
#  @param data      Bytestring to be sent to socket
#  @param pool_name Name of pool bound to Python socket for CnC/TC communication
def Datasend(data, pool_name):
    """

    :param data:
    :param pool_name:
    :return:
    """
    pmgr = dbus_connection('poolmanager', communication['poolmanager'])

    if not pmgr:
        return

    if _has_tc_connection(pool_name, pmgr):
        pmgr.Functions('tc_send', pool_name, data)


##
#  Limits check
#
#  Check if TM parameter is within specified limits. Return 0 if ok, 1 if out of soft limit, 2 if out of hard limit.
#  @param param OCF_NAME
#  @param val   Parameter value
def Tm_limits_check(param, val, user_limit: dict = None, dbcon=None):
    """

    :param param:
    :param val:
    :param user_limit:
    :param dbcon:
    :return:
    """
    if user_limit is not None:
        val = float(val)
        limits = [user_limit[i][0] <= val <= user_limit[i][1] for i in user_limit]

        if not any(limits):
            return 2
        elif all(limits):
            return 0
        else:
            return 1

    dbcon = scoped_session_idb
    que = 'SELECT ocf_nbool,ocf_codin,ocp_pos,ocp_type,ocp_lvalu,ocp_hvalu from ocf\
            left join ocp on ocf_name=ocp_name where ocf_name="%s"' % param
    dbres = dbcon.execute(que)
    oc = dbres.fetchall()
    dbcon.close()
    if len(oc) == 0:
        return 0
    fmt = oc[0][1]
    if oc[0][3] == 'C':
        return 2 if val not in [i[4] for i in oc] else 0
    elif oc[0][3] in ['S', 'H']:
        oolimits = [str_to_num(pval[4], fmt) <= str_to_num(val, fmt) <= str_to_num(pval[5], fmt) for
                    pval in oc]
        if not any(oolimits):
            return 2
        elif all(oolimits):
            return 0
        elif any(oolimits) and ([lt[3] for lt in oc].count('S') == 0):
            return 0
        else:
            return 1


##
#  st_to_num
#
#  Convert string to either int or float, return input str if fails
#  @param string input string
#  @param fmt    format specifier for conversion, 'I' for int, 'R' for float
def str_to_num(string, fmt=None):
    """

    :param string:
    :param fmt:
    :return:
    """
    if fmt == 'I':
        num = int(string)
    elif fmt == 'R':
        num = float(string)
    else:
        return string
    return num


def calc_param_crc(cmd, *args, no_check=False, hack_value=None):
    """
    Calculates the CRC over the packet source data (excluding the checksum parameter).
    Uses the same CRC algo as packet CRC and assumes the checksum is at the end of the packet source data.

    :param cmd:
    :param args:
    :param no_check:
    :param hack_value:
    :return:
    """
    pdata = Tcbuild(cmd, *args, no_check=no_check, hack_value=hack_value, source_data_only=True)
    return crc(pdata[:-PEC_LEN])


def load_to_memory(data, memid, memaddr, max_pkt_size=MAX_PKT_LEN, sleep=0.125, ack=0b1001, pool_name='LIVE', tcname=None,
                   progress=True, calc_crc=True, byte_align=4):
    """
    Function for loading data to DPU memory. Splits the input _data_ into slices and sequentially sends them
    to the specified location _memid_, _mempos_ by repeatedly calling the _Tcsend_bytes_ function until
    all _data_ is transferred. Data is zero-padded if not aligned to _byte_align_ bytes.

    :param data:
    :param memid:
    :param memaddr:
    :param max_pkt_size:
    :param sleep:
    :param ack:
    :param pool_name:
    :param tcname:
    :param progress:
    :param calc_crc:
    :param byte_align:
    :return:
    """

    if not isinstance(data, bytes):
        if isinstance(data, str):
            data = open(data, 'rb').read()
        else:
            raise TypeError('Data is not bytes or str')

    if byte_align and (len(data) % byte_align):
        logger.warning('Data is not {}-byte aligned, padding.'.format(byte_align))
        data += bytes(byte_align - (len(data) % byte_align))

    # get service 6,2 info from MIB
    apid, memid_ref, fmt, endspares = _get_upload_service_info(tcname)
    pkt_overhead = TC_HEADER_LEN + struct.calcsize(fmt) + len(endspares) + PEC_LEN
    payload_len = max_pkt_size - pkt_overhead

    memid = get_mem_id(memid, memid_ref)

    # get permanent pmgr handle to avoid requesting one for each packet
    pmgr = _get_pmgr_handle(tc_pool=pool_name)

    data_size = len(data)
    startaddr = memaddr

    upload_bytes = b''
    pcnt = 0
    ptot = None

    slices = [data[i:i + payload_len] for i in range(0, len(data), payload_len)]
    if (payload_len + pkt_overhead) > MAX_PKT_LEN:
        logger.warning('PKTSIZE > {} bytes, this might not work!'.format(MAX_PKT_LEN))

    for sli in slices:
        t1 = time.time()

        # create PUS packet
        packetdata = struct.pack(fmt, memid, startaddr, len(sli)) + sli + endspares
        seq_cnt = counters.setdefault(apid, 0)
        puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=seq_cnt, ack=ack)

        if len(puspckt) > MAX_PKT_LEN:
            logger.warning('Packet length ({}) exceeding MAX_PKT_LEN of {} bytes!'.format(len(puspckt), MAX_PKT_LEN))

        Tcsend_bytes(puspckt, pool_name=pool_name, pmgr_handle=pmgr)
        # collect all uploaded segments for CRC at the end
        upload_bytes += sli
        pcnt += 1

        if progress:
            if ptot is None:
                ptot = int(np.ceil(data_size / len(sli)))  # packets needed to transfer data
            print('{}/{} packets sent\r'.format(pcnt, ptot), end='')

        dt = time.time() - t1
        time.sleep(max(sleep - dt, 0))

        startaddr += len(sli)
        counters[apid] += 1

    print('\nUpload finished, {} bytes sent in {} packets.'.format(len(upload_bytes), pcnt))

    if calc_crc:
        # return total length of uploaded data  and CRC over entire uploaded data
        return len(upload_bytes), crc(upload_bytes)


def get_tc_descr_from_stsst(st, sst):
    """

    :param st:
    :param sst:
    :return:
    """
    res = scoped_session_idb.execute('SELECT ccf_descr FROM ccf where ccf_type={} and ccf_stype={}'.format(st, sst)).fetchall()
    return [x[0] for x in res]


def bin_to_hex(fname, outfile):
    """

    :param fname:
    :param outfile:
    """
    # bash alternative: hexdump -e '16/1 "%3.2X"' fname > outfile
    bindata = open(fname, 'rb').read()
    buf = prettyhex(bindata)
    with open(outfile, 'w') as fd:
        fd.write(buf)
        # print('Wrote {} bytes as HEX-ASCII to {}.'.format(len(bindata), outfile))
        logger.info('Wrote {} bytes as HEX-ASCII to {}.'.format(len(bindata), outfile))


def get_mem_id(memid, memid_ref):
    """

    :param memid:
    :param memid_ref:
    :return:
    """
    if not isinstance(memid, int):
        dbcon = scoped_session_idb
        dbres = dbcon.execute('SELECT pas_alval from pas where pas_numbr="{}" and pas_altxt="{}"'.format(memid_ref, memid))
        try:
            memid, = dbres.fetchall()[0]
        except IndexError:
            que = 'SELECT pas_altxt from pas where pas_numbr="{}"'.format(memid_ref)
            alvals = [x[0] for x in dbcon.execute(que).fetchall()]
            raise ValueError('Invalid MemID "{}". Allowed values are: {}.'.format(memid, ', '.join(alvals)))
        finally:
            dbcon.close()
        memid = int(memid)

    return memid


#######################################################
##
#  Convert srec file to sequence of PUS packets (TM6,2) and save them in hex-files or send them to socket _tcsend_
#  @param fname        Input srec file
#  @param outname      Root name ouf the output files, if _None_, _fname_ is used
#  @param memid        Memory ID packets are destined to, number or name (e.g. "DPU_RAM")
#  @param memaddr      Memory start address where packets are patched to
#  @param segid        Segment ID
#  @param tcsend       Name of pool bound to TC socket to send the packets to, files are created instead if _False_
#  @param linesperpack Number of lines in srec file to concatenate in one PUS packet
#  @param pcount       Initial sequence counter for packets
#  @param sleep        Timeout after each packet if packets are sent directly to socket
def srectohex(fname, memid, memaddr, segid, tcsend=False, outname=None, linesperpack=61, pcount=0, sleep=0.,
              source_only=False, add_memaddr_to_source=False):
    """

    :param fname:
    :param memid:
    :param memaddr:
    :param segid:
    :param tcsend:
    :param outname:
    :param linesperpack:
    :param pcount:
    :param sleep:
    :param source_only:
    :param add_memaddr_to_source:
    :return:
    """
    source_list = []
    if outname is None:
        outname = fname.replace('.srec', '')

    # get service 6,2 info from MIB
    apid, memid_ref, fmt, endspares = _get_upload_service_info()

    if not isinstance(memid, int):
        dbcon = scoped_session_idb
        dbres = dbcon.execute('SELECT pas_alval from pas where pas_numbr="{}" and pas_altxt="{}"'.format(memid_ref, memid))
        try:
            memid, = dbres.fetchall()[0]
        except IndexError:
            raise ValueError('MemID "{}" does not exist. Aborting.'.format(memid))
        finally:
            dbcon.close()
        memid = int(memid)

    f = open(fname, 'r').readlines()[1:]
    lines = [p[12:-3] for p in f]
    startaddr = int(f[0][4:12], 16)

    # npacks=len(lines)//int(linesperpack)
    if not isinstance(pcount, int):
        pcount = 0

    linecount = 0
    while linecount < len(f) - 1:

        t1 = time.time()

        linepacklist = []
        for n in range(linesperpack):
            if linecount >= (len(lines) - 1):
                break
            linepacklist.append(lines[linecount])
            linelength = len(lines[linecount]) // 2
            if int(f[linecount + 1][4:12], 16) != (int(f[linecount][4:12], 16) + linelength):
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)
                break
            else:
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)

        linepack = bytes.fromhex(''.join(linepacklist))
        dlen = len(linepack)
        data = struct.pack(SEG_HEADER_FMT, segid, startaddr, dlen // 4) + linepack + bytes(SEG_SPARE_LEN)
        data = data + crc(data).to_bytes(SEG_CRC_LEN, 'big')
        if source_only:
            if add_memaddr_to_source:
                source_list.append(prettyhex(memaddr.to_bytes(4, 'big') + data))
            else:
                source_list.append(prettyhex(data))
            startaddr = newstartaddr
            memaddr += len(data)
            continue
        packetdata = struct.pack('>HII', memid, memaddr, len(data)) + data
        PUS = Tcpack(data=packetdata, st=6, sst=2, sc=pcount, apid=apid, ack=0b1001)
        if len(PUS) > 1024:
            logger.warning('Packet length ({:}) exceeding 1024 bytes!'.format(len(PUS)))
        if tcsend:
            Tcsend_bytes(PUS, pool_name=tcsend)
            dt = time.time() - t1
            time.sleep(max(sleep - dt, 0))
        else:
            with open(outname + '%04i.tc' % pcount, 'w') as ofile:
                # ofile.write(PUS.hex.upper())
                ofile.write(prettyhex(PUS))
        startaddr = newstartaddr
        # startaddr += dlen
        memaddr += len(data)
        pcount += 1
    if source_only:
        if add_memaddr_to_source:
            source_list.append(prettyhex(memaddr.to_bytes(4, 'big') + bytes(12)))
        else:
            source_list.append(prettyhex(bytes(12)))
        with open(outname + '_source.TC', 'w') as fd:
            fd.write('\n'.join(source_list))
        return
    packetdata = struct.pack('>HII', memid, memaddr, 12) + bytes(12)
    PUS = Tcpack(data=packetdata, st=6, sst=2, sc=pcount, apid=apid, ack=0b1001)
    if tcsend:
        Tcsend_bytes(PUS, pool_name=tcsend)
    else:
        with open(outname + '%04i.tc' % pcount, 'w') as ofile:
            # ofile.write(PUS.hex.upper())
            ofile.write(prettyhex(PUS))


def srectosrecmod(input_srec, output_srec, imageaddr=0x40180000, linesperpack=61):
    """
    Repack source data from srec file into 'DBS structure' and save it to new srec file.

    :param input_srec:
    :param output_srec:
    :param imageaddr:
    :param linesperpack:
    :return:
    """
    # get source data from original srec and add memory address
    srectohex(input_srec, outname='srec_binary', memaddr=0xDEADBEEF, source_only=True, linesperpack=linesperpack)

    # write source data to new srec
    source_to_srec('srec_binary_source.TC', output_srec, memaddr=imageaddr)


def srec_to_s6(fname, memid, memaddr, segid, tcname=None, linesperpack=50, max_pkt_size=MAX_PKT_LEN, image_crc=True):
    # get service 6,2 info from MIB
    apid, memid_ref, fmt, endspares = _get_upload_service_info(tcname)
    pkt_overhead = TC_HEADER_LEN + struct.calcsize(fmt) + SEG_HEADER_LEN + SEG_SPARE_LEN + SEG_CRC_LEN + len(
        endspares) + PEC_LEN
    payload_len = max_pkt_size - pkt_overhead

    memid = get_mem_id(memid, memid_ref)

    pckts = []

    f = open(fname, 'r').readlines()[1:]
    lines = [p[12:-3] for p in f]
    data_size = len(''.join(lines)) // 2
    startaddr = int(f[0][4:12], 16)

    upload_bytes = b''
    linecount = 0
    bcnt = 0
    pcnt = 0
    ptot = None

    while linecount < len(f) - 1:

        t1 = time.time()

        linepacklist = []
        for n in range(linesperpack):
            if linecount >= (len(lines) - 1):
                break

            if (len(''.join(linepacklist)) + len(lines[linecount])) // 2 > payload_len:  # ensure max_pkt_size
                break

            linepacklist.append(lines[linecount])
            linelength = len(lines[linecount]) // 2
            if int(f[linecount + 1][4:12], 16) != (int(f[linecount][4:12], 16) + linelength):
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)
                break
            else:
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)

        linepack = bytes.fromhex(''.join(linepacklist))
        dlen = len(linepack)
        bcnt += dlen
        # segment header, see IWF DBS HW SW ICD
        data = struct.pack(SEG_HEADER_FMT, segid, startaddr, dlen // 4) + linepack + bytes(SEG_SPARE_LEN)
        data = data + crc(data).to_bytes(SEG_CRC_LEN, 'big')

        # create PUS packet
        packetdata = struct.pack(fmt, memid, memaddr, len(data)) + data + endspares
        seq_cnt = counters.setdefault(apid, 0)
        puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=seq_cnt, ack=0b1001)

        if len(puspckt) > MAX_PKT_LEN:
            logger.warning('Packet length ({}) exceeding MAX_PKT_LEN of {} bytes!'.format(len(puspckt), MAX_PKT_LEN))

        pckts.append(puspckt)

        # collect all uploaded segments for CRC at the end
        upload_bytes += data
        pcnt += 1

        startaddr = newstartaddr
        memaddr += len(data)
        counters[apid] += 1

    packetdata = struct.pack(fmt, memid, memaddr, 12) + bytes(12) + endspares
    puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=counters[apid], ack=0b1001)
    counters[apid] += 1
    pckts.append(puspckt)

    if image_crc:
        # return total length of uploaded data (without termination segment) and CRC over entire image, including segment headers
        return pckts, len(upload_bytes), crc(upload_bytes)

    return pckts


def upload_srec(fname, memid, memaddr, segid, pool_name='LIVE', tcname=None, linesperpack=50, sleep=0.125,
                max_pkt_size=MAX_PKT_LEN, progress=True, image_crc=True):
    """
    Upload data from an SREC file to _memid_ via S6,2

    :param fname:
    :param memid:
    :param memaddr:
    :param segid:
    :param pool_name:
    :param tcname:
    :param linesperpack:
    :param sleep:
    :param max_pkt_size:
    :param progress:
    :param image_crc:
    """
    # get service 6,2 info from MIB
    apid, memid_ref, fmt, endspares = _get_upload_service_info(tcname)
    pkt_overhead = TC_HEADER_LEN + struct.calcsize(fmt) + SEG_HEADER_LEN + SEG_SPARE_LEN + SEG_CRC_LEN + len(endspares) + PEC_LEN
    payload_len = max_pkt_size - pkt_overhead

    memid = get_mem_id(memid, memid_ref)

    # get permanent pmgr handle to avoid requesting one for each packet
    pmgr = _get_pmgr_handle(tc_pool=pool_name)

    f = open(fname, 'r').readlines()[1:]
    lines = [p[12:-3] for p in f]
    data_size = len(''.join(lines)) // 2
    startaddr = int(f[0][4:12], 16)

    upload_bytes = b''
    linecount = 0
    bcnt = 0
    pcnt = 0
    ptot = None

    while linecount < len(f) - 1:

        t1 = time.time()

        linepacklist = []
        for n in range(linesperpack):
            if linecount >= (len(lines) - 1):
                break

            if (len(''.join(linepacklist)) + len(lines[linecount])) // 2 > payload_len:  # ensure max_pkt_size
                break

            linepacklist.append(lines[linecount])
            linelength = len(lines[linecount]) // 2
            if int(f[linecount + 1][4:12], 16) != (int(f[linecount][4:12], 16) + linelength):
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)
                break
            else:
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)

        linepack = bytes.fromhex(''.join(linepacklist))
        dlen = len(linepack)
        bcnt += dlen
        # segment header, see IWF DBS HW SW ICD
        data = struct.pack(SEG_HEADER_FMT, segid, startaddr, dlen // 4) + linepack + bytes(SEG_SPARE_LEN)
        data = data + crc(data).to_bytes(SEG_CRC_LEN, 'big')

        # create PUS packet
        packetdata = struct.pack(fmt, memid, memaddr, len(data)) + data + endspares
        seq_cnt = counters.setdefault(apid, 0)
        puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=seq_cnt, ack=0b1001)

        if len(puspckt) > MAX_PKT_LEN:
            logger.warning('Packet length ({}) exceeding MAX_PKT_LEN of {} bytes!'.format(len(puspckt), MAX_PKT_LEN))

        Tcsend_bytes(puspckt, pool_name=pool_name, pmgr_handle=pmgr)
        # collect all uploaded segments for CRC at the end
        upload_bytes += data
        pcnt += 1

        if progress:
            if ptot is None:
                ptot = int(np.ceil(data_size / dlen))  # packets needed to transfer SREC payload
            print('{}/{} packets sent\r'.format(pcnt, ptot), end='')

        dt = time.time() - t1
        time.sleep(max(sleep - dt, 0))

        startaddr = newstartaddr
        memaddr += len(data)
        counters[apid] += 1

    # send all-zero termination segment of length 12
    packetdata = struct.pack(fmt, memid, memaddr, 12) + bytes(12) + endspares
    puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=counters[apid], ack=0b1001)
    Tcsend_bytes(puspckt, pool_name=pool_name, pmgr_handle=pmgr)
    counters[apid] += 1

    print('\nUpload finished, {} bytes sent in {}(+1) packets.'.format(bcnt, pcnt))

    if image_crc:
        # return total length of uploaded data (without termination segment) and CRC over entire image, including segment headers
        return len(upload_bytes), crc(upload_bytes)


def segment_data(data, segid, addr, seglen=480):
    """
    Split data into segments (as defined in IWF DPU HW SW ICD) with segment header and CRC.
    Segment data has to be two-word aligned.

    :param data:
    :param segid:
    :param addr:
    :param seglen:
    :return: list of segments
    """

    if isinstance(data, str):
        data = open(data, 'rb').read()

    if not isinstance(data, bytes):
        raise TypeError
        
    datalen = len(data)
    if datalen % 4:
        raise ValueError('Data length is not two-word aligned')
    data = io.BytesIO(data)
    
    segments = []
    segaddr = addr
    
    while data.tell() < datalen:
        chunk = data.read(seglen - (SEG_HEADER_LEN + SEG_SPARE_LEN + SEG_CRC_LEN))
        chunklen = len(chunk)

        if chunklen % 4:
            raise ValueError('Segment data length is not two-word aligned')
            
        sdata = struct.pack(SEG_HEADER_FMT, segid, segaddr, chunklen // 4) + chunk + bytes(SEG_SPARE_LEN)
        sdata += crc(sdata).to_bytes(SEG_CRC_LEN, 'big')
        segments.append(sdata)
        segaddr += chunklen

    # add 12 byte termination segment
    segments.append(bytes(SEG_HEADER_LEN))
    
    return segments


def source_to_srec(data, outfile, memaddr, header=None, bytes_per_line=32, skip_bytes=0):
    """

    :param data:
    :param outfile:
    :param memaddr:
    :param header:
    :param bytes_per_line:
    :param skip_bytes:
    :return:
    """

    def srec_chksum(x):
        """

        :param x:
        :return:
        """
        return sum(bytes.fromhex(x)) & 0xff ^ 0xff

    if bytes_per_line > SREC_MAX_BYTES_PER_LINE:
        raise ValueError("Maximum number of bytes per line is {}!".format(SREC_MAX_BYTES_PER_LINE))

    if isinstance(data, str):
        data = open(data, 'rb').read()
        
    if not isinstance(data, bytes):
        raise TypeError

    data = data[skip_bytes:]

    if header is None:
        fname = outfile.split('/')[-1][-60:]
        header = 'S0{:02X}0000{:}'.format(len(fname.encode('ascii')) + 3, fname.encode('ascii').ljust(24).hex().upper())
        header += '{:02X}'.format(srec_chksum(header[2:]))

    datalen = len(data)
    data = io.BytesIO(data)

    sreclist = []
    terminator = 'S705{:08X}'.format(memaddr)
    terminator += '{:02X}'.format(srec_chksum(terminator[2:]))

    while data.tell() < datalen:
        chunk = data.read(bytes_per_line)
        chunklen = len(chunk)
        line = '{:02X}{:08X}{:}'.format(chunklen + 5, memaddr, chunk.hex().upper())
        # add chksum according to SREC standard
        line = 'S3' + line + '{:02X}'.format(srec_chksum(line))
        sreclist.append(line)
        memaddr += chunklen

    with open(outfile, 'w') as fd:
        fd.write(header + '\n')
        fd.write('\n'.join(sreclist) + '\n')
        fd.write(terminator)

    print('Data written to file: "{}", skipped first {} bytes.'.format(outfile, skip_bytes))
    logger.info('Data written to file: "{}", skipped first {} bytes.'.format(outfile, skip_bytes))


def srec_direct(fname, memid, pool_name='LIVE', max_pkt_size=MAX_PKT_LEN, tcname=None, sleep=0.125, progress=True,
                image_crc=True, byte_align=2, ack=0b1001, dryrun=False):
    """
    Upload data from SREC file directly to memory _memid_, no additional segment headers (like for DBS) are added.

    :param fname:
    :param memid:
    :param pool_name:
    :param max_pkt_size:
    :param tcname:
    :param sleep:
    :param progress:
    :param image_crc:
    :param byte_align:
    :param ack:
    :param dryrun:
    :return:
    """
    if dryrun:
        print('DRYRUN -- NO PACKETS ARE BEING SENT!')

    # get service 6,2 info from MIB
    apid, memid_ref, fmt, endspares = _get_upload_service_info(tcname)
    pkt_overhead = TC_HEADER_LEN + struct.calcsize(fmt) + len(endspares) + PEC_LEN
    payload_len = max_pkt_size - pkt_overhead

    memid = get_mem_id(memid, memid_ref)

    # get permanent pmgr handle to avoid requesting one for each packet
    if not dryrun:
        pmgr = _get_pmgr_handle(tc_pool=pool_name)

    upload_bytes = b''
    bcnt = 0
    pcnt = 0
    ptot = None

    f = open(fname, 'r').readlines()[1:-1]  # omit header and footer line
    lines = [p[12:-3] for p in f]
    data_size = len(''.join(lines)) // 2
    memaddr = int(f[0][4:12], 16)

    linecount = 0
    nextlinelength = len(lines[linecount]) // 2
    while linecount < len(f) - 1:

        t1 = time.time()

        linepacklist = []
        packlen = 0
        while (packlen + nextlinelength) <= payload_len:
            if linecount >= (len(lines) - 1):
                break
            linepacklist.append(lines[linecount])
            linelength = len(lines[linecount]) // 2
            packlen += linelength
            if int(f[linecount + 1][4:12], 16) != (int(f[linecount][4:12], 16) + linelength):
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)
                break
            else:
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)

            nextlinelength = len(lines[linecount]) // 2

        data = bytes.fromhex(''.join(linepacklist))

        dlen = len(data)
        bcnt += dlen

        # create PUS packet
        packetdata = struct.pack(fmt, memid, memaddr, len(data)) + data + endspares
        seq_cnt = counters.setdefault(apid, 0)
        puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=seq_cnt, ack=ack)

        if len(puspckt) > MAX_PKT_LEN:
            logger.warning('Packet length ({}) exceeding MAX_PKT_LEN of {} bytes!'.format(len(puspckt), MAX_PKT_LEN))

        if not dryrun:
            Tcsend_bytes(puspckt, pool_name=pool_name, pmgr_handle=pmgr)

        # collect all uploaded segments for CRC at the end
        upload_bytes += data
        pcnt += 1

        if progress:
            if ptot is None:
                ptot = int(np.ceil(data_size / dlen))  # packets needed to transfer SREC payload
            print('{}/{} packets sent\r'.format(pcnt, ptot), end='')

        dt = time.time() - t1
        time.sleep(max(sleep - dt, 0))

        if data == b'':
            print('No data left, exit upload.')
            return

        memaddr = newstartaddr
        if not dryrun:
            counters[apid] += 1

    # check if entire data is x-byte-aligned
    if len(upload_bytes) % byte_align:
        padding = byte_align - (len(upload_bytes) % byte_align)
        print('\nData is not {}-byte aligned. Sending padding data ({})'.format(byte_align, padding))

        # create PUS packet
        packetdata = struct.pack(fmt, memid, memaddr, padding) + bytes(padding) + endspares
        seq_cnt = counters.setdefault(apid, 0)
        puspckt = Tcpack(data=packetdata, st=6, sst=2, apid=apid, sc=seq_cnt, ack=ack)

        if not dryrun:
            Tcsend_bytes(puspckt, pool_name=pool_name, pmgr_handle=pmgr)
            counters[apid] += 1

        memaddr += padding
        upload_bytes += bytes(padding)
        bcnt += padding
        pcnt += 1

    print('\nUpload finished, {} bytes sent in {} packets.'.format(bcnt, pcnt))

    if image_crc:
        # return total length of uploaded data (without termination segment) and CRC over entire image, including segment headers
        return len(upload_bytes), crc(upload_bytes)


def _get_upload_service_info(tcname=None):
    """
    Get info about service 6,2 from MIB

    :param tcname:
    :return:
    """
    if tcname is None:
        cmd = get_tc_descr_from_stsst(6, 2)[0]
    else:
        cmd = tcname

    params = _get_tc_params(cmd, paf_cal=True)

    apid = params[0][2]

    # try to find paf_ref for MEMID
    try:
        memid_ref = [p[-1] for p in params if p[-1] is not None][0]
    except KeyError:
        memid_ref = None

    # get format info for fixed block
    fmt = '>'
    idx = 0
    for par in params:
        fmt += ptt(*par[8:10])
        if par[4] != 0:
            idx = params.index(par)
            break

    # check for spares after variable part
    endspares = b''
    for par in params[idx:]:
        if par[5] == 'A':
            endspares += bytes(par[6] // 8)

    return apid, memid_ref, fmt, endspares


def get_tc_list(ccf_descr=None):
    """

    :param ccf_descr:
    :return:
    """
    if ccf_descr is None:
        cmds = scoped_session_idb.execute('SELECT ccf_cname, ccf_descr, ccf_descr2, ccf_type, ccf_stype, ccf_npars, '
                                          'cpc_descr, cpc_dispfmt, cdf_eltype, cpc_pname, cdf_value, cpc_inter, '
                                          'cpc_radix FROM ccf LEFT JOIN cdf ON cdf.cdf_cname=ccf.ccf_cname '
                                          'LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname '
                                          'ORDER BY SUBSTRING(ccf_cname, 1, 2), ccf_type, ccf_stype, ccf_cname').fetchall()
    else:
        cmds = scoped_session_idb.execute('SELECT ccf_cname, ccf_descr, ccf_descr2, ccf_type, ccf_stype, ccf_npars, '
                                          'cpc_descr, cpc_dispfmt, cdf_eltype, cpc_pname, cdf_value, cpc_inter, '
                                          'cpc_radix FROM ccf LEFT JOIN cdf ON cdf.cdf_cname=ccf.ccf_cname '
                                          'LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname '
                                          'WHERE ccf_descr="{}"'.format(ccf_descr)).fetchall()

    scoped_session_idb.close()

    cmd_dict = {}

    for row in cmds:
        cmd_dict.setdefault(row[0:5], []).append(row[6:])

    return cmd_dict


def get_tc_calibration_and_parameters(ccf_descr=None):
    """

    :param ccf_descr:
    :return:
    """
    if ccf_descr is None:
        calibrations = scoped_session_idb.execute('SELECT ccf_cname, ccf_descr, cdf_eltype, cdf_descr, cdf_ellen, '
                                                  'cdf_value, cdf_pname, cpc_descr, cpc_categ, cpc_ptc, '
                                                  'cpc_pfc, prv_minval, prv_maxval, pas_altxt, pas_alval '
                                                  'FROM ccf LEFT JOIN cdf ON ccf.ccf_cname=cdf.cdf_cname '
                                                  'LEFT JOIN cpc ON cdf.cdf_pname=cpc.cpc_pname '
                                                  'LEFT JOIN prv ON cpc.cpc_prfref=prv.prv_numbr '
                                                  'LEFT JOIN pas ON cpc.cpc_pafref=pas.pas_numbr '
                                                  'ORDER BY ccf_type, ccf_stype, '
                                                  'ccf_cname, cdf_bit, pas_alval').fetchall()

    else:
        calibrations = scoped_session_idb.execute('SELECT ccf_cname, ccf_descr, cdf_eltype, cdf_descr, cdf_ellen, '
                                                  'cdf_value, cdf_pname, cpc_descr, cpc_categ, cpc_ptc, '
                                                  'cpc_pfc, prv_minval, prv_maxval, pas_altxt, pas_alval '
                                                  'FROM ccf LEFT JOIN cdf ON ccf.ccf_cname=cdf.cdf_cname '
                                                  'LEFT JOIN cpc ON cdf.cdf_pname=cpc.cpc_pname '
                                                  'LEFT JOIN prv ON cpc.cpc_prfref=prv.prv_numbr '
                                                  'LEFT JOIN pas ON cpc.cpc_pafref=pas.pas_numbr '
                                                  'WHERE ccf_descr="{}"'.format(ccf_descr)).fetchall()

    scoped_session_idb.close()

    calibrations_dict = {}

    for row in calibrations:
        calibrations_dict.setdefault(row[:9], []).append(row[9:])

    return calibrations_dict


def get_tm_parameter_list(st, sst, apid=None, pi1val=0):
    """

    :param st:
    :param sst:
    :param apid:
    :param pi1val:
    :return:
    """
    spid, tpsd = _get_spid(st, sst, apid=apid, pi1val=pi1val)

    if tpsd == -1:
        que = 'SELECT plf_name, pcf_descr, plf_offby, pcf_ptc, pcf_pfc FROM plf LEFT JOIN pcf ON plf_name=pcf_name WHERE plf_spid={} ORDER BY plf_offby, plf_offbi'.format(spid)
    else:
        que = 'SELECT vpd_name, pcf_descr, NULL, pcf_ptc, pcf_pfc FROM vpd LEFT JOIN pcf ON vpd_name=pcf_name WHERE vpd_tpsd={} ORDER BY vpd_pos'.format(tpsd)

    res = scoped_session_idb.execute(que).fetchall()

    return res


def get_tm_parameter_info(pname):
    """

    :param pname:
    :return:
    """
    que = 'SELECT ocp_lvalu, ocp_hvalu, ocp_type, txp_from, txp_altxt FROM pcf LEFT JOIN ocp ON pcf_name=ocp_name ' \
          'LEFT JOIN txp ON pcf_curtx=txp_numbr WHERE pcf_name="{}" ORDER BY txp_from, ocp_pos'.format(pname)
    res = scoped_session_idb.execute(que).fetchall()

    return res


def pcf_name_to_descr(pcfname):
    """
    Look up PCF_DESCR for PCF_NAME in MIB
    """

    if pcfname in _pcf_descr_cache:
        return _pcf_descr_cache[pcfname]

    que = 'SELECT pcf_descr FROM pcf WHERE pcf_name="{}"'.format(pcfname)
    res = scoped_session_idb.execute(que).fetchall()

    if res:
        _pcf_descr_cache[pcfname] = res[0][0]
        return res[0][0]


def get_tm_id(pcf_descr=None):
    """

    :param pcf_descr:
    :return:
    """
    if pcf_descr is None:
        tms = scoped_session_idb.execute('SELECT pid_type, pid_stype, pid_apid, pid_pi1_val, pid_descr, pid_tpsd, '
                                         'pid_spid, pcf_name, pcf_descr, pcf_curtx, txp_from, txp_altxt, plf_offby,'
                                         'pcf_ptc, pcf_pfc '
                                         'FROM pid '
                                         'LEFT JOIN plf '
                                         'ON pid_spid = plf_spid AND pid_tpsd = -1 '
                                         'LEFT JOIN vpd '
                                         'ON pid_tpsd = vpd_tpsd AND pid_tpsd <> -1 '
                                         'LEFT JOIN pcf '
                                         'ON pcf_name = COALESCE(plf_name, vpd_name) '
                                         'LEFT JOIN txf '
                                         'ON pcf_curtx = txf_numbr '
                                         'LEFT JOIN txp '
                                         'ON txf_numbr = txp.txp_numbr '
                                         'ORDER BY pid_type, pid_stype, pid_apid, pid_pi1_val').fetchall()

    else:
        tms = scoped_session_idb.execute('SELECT pid_type, pid_stype, pid_apid, pid_pi1_val, pid_descr , pid_tpsd, '
                                         'pid_spid, pcf_name, pcf_descr, pcf_curtx, txp_from, txp_altxt, plf_offby,'
                                         'pcf_ptc, pcf_pfc '
                                         'FROM pid '
                                         'LEFT JOIN plf '
                                         'ON pid_spid = plf_spid AND pid_tpsd = -1 '
                                         'LEFT JOIN vpd '
                                         'ON pid_tpsd = vpd_tpsd AND pid_tpsd <> -1 '
                                         'LEFT JOIN pcf '
                                         'ON pcf_name = COALESCE(plf_name, vpd_name) '
                                         'LEFT JOIN txf '
                                         'ON pcf_curtx = txf_numbr '
                                         'LEFT JOIN txp '
                                         'ON txf_numbr = txp.txp_numbr '
                                         'WHERE pcf_descr="{}"'.format(pcf_descr)).fetchall()

    scoped_session_idb.close()

    tms_dict = {}

    for row in tms:
        tms_dict.setdefault(row[0:5], []).append(row[5:])

    return tms_dict


def get_tm_parameter_sizes(st, sst, apid=None, pi1val=0):
    """
    Returns a list of parameters and their sizes. For variable length TMs only the first fixed part is considered.

    :param st:
    :param sst:
    :param apid:
    :param pi1val:
    :return:
    """

    spid, tpsd = _get_spid(st, sst, apid=apid, pi1val=pi1val)

    if tpsd == -1:
        que = 'SELECT plf_name, pcf_descr, pcf_ptc, pcf_pfc, NULL FROM plf LEFT JOIN pcf ON plf_name=pcf_name WHERE plf_spid={} ORDER BY plf_offby, plf_offbi'.format(spid)
    else:
        que = 'SELECT vpd_name, pcf_descr, pcf_ptc, pcf_pfc, vpd_grpsize FROM vpd LEFT JOIN pcf ON vpd_name=pcf_name WHERE vpd_tpsd={} ORDER BY vpd_pos'.format(tpsd)

    res = scoped_session_idb.execute(que).fetchall()

    pinfo = []
    for p in res:
        pinfo.append((p[1], csize(ptt(*p[2:4]))))
        # break after first "counter" parameter
        if p[-1] != 0:
            break

    return pinfo


def _get_spid(st, sst, apid=None, pi1val=0):
    """

    :param st:
    :param sst:
    :param apid:
    :param pi1val:
    :return:
    """
    if apid is None:
        apid = ''
    else:
        apid = ' AND pid_apid={}'.format(apid)

    que = 'SELECT pid_spid, pid_tpsd FROM pid WHERE pid_type={} AND pid_stype={}{} AND pid_pi1_val={}'.format(st, sst, apid, pi1val)
    spid, tpsd = scoped_session_idb.execute(que).fetchall()[0]

    return spid, tpsd


def get_data_pool_items(pcf_descr=None, src_file=None, as_dict=False):
    """

    :param pcf_descr:
    :param src_file:
    :param as_dict:
    :return:
    """
    if not isinstance(src_file, (str, type(None))):
        raise TypeError('src_file must be str, is {}.'.format(type(src_file)))

    if src_file:
        with open(src_file, 'r') as fd:
            lines = fd.readlines()[2:]  # skip first two header rows
        data_pool = []
        for line in lines:
            if not line.startswith('#'):
                dp_item = line.strip().split('|')
                # check for format
                if len(dp_item) == 9:
                    data_pool.append(dp_item[:2][::-1] + [dp_item[2]] + [dp_item[4]] + dp_item[6:8])  # PID, NAME, TYPE, MULT, VALUE, DESCR
                else:
                    raise ValueError('Wrong format of input line in {}.'.format(src_file))

        if as_dict:
            data_pool_dict = {int(row[0]): {'descr': row[1], 'fmt': fmtlist[row[2]]} for row in data_pool if row[2] in fmtlist}
            if len(data_pool_dict) != len(data_pool):
                logger.warning('Data pool items were rejected because of unknown format ({})'.format(len(data_pool) - len(data_pool_dict)))
            return data_pool_dict
        else:
            return data_pool, src_file

    elif pcf_descr is None and not src_file:
        data_pool = scoped_session_idb.execute('SELECT pcf_pid, pcf_descr, pcf_ptc, pcf_pfc '
                                               'FROM pcf WHERE pcf_pid IS NOT NULL').fetchall()

    else:
        data_pool = scoped_session_idb.execute('SELECT pcf_pid, pcf_descr, pcf_ptc, pcf_pfc '
                                               'FROM pcf WHERE pcf_pid IS NOT NULL AND pcf_descr="{}"'.format(pcf_descr)).fetchall()

    scoped_session_idb.close()

    if not as_dict:
        return data_pool, src_file

    data_pool_dict = {int(row[0]): {'descr': row[1], 'fmt': ptt(row[2], row[3])} for row in data_pool}

    # for row in data_pool:
    #     data_pool_dict.setdefault(row[0:4], []).append(row[5:])

    return data_pool_dict


def get_dp_fmt_info(dp_name):
    """

    :param dp_name:
    :return:
    """
    que = 'SELECT pcf_name FROM pcf where pcf_pid is not NULL and pcf_descr="{}"'.format(dp_name)
    mib_name = scoped_session_idb.execute(que).fetchall()[0]
    return mib_name


# def get_dp_items(source='mib'):
#     fmt = {3: {4: 'UINT8', 12: 'UINT16', 14: 'UINT32'}, 4: {4: 'INT8', 12: 'INT16', 14: 'INT32'}, 5: {1: 'FLOAT'}, 9: {18: 'CUC'}, 7: {1: '1OCT'}}
#
#     if source.lower() == 'mib':
#         dp = scoped_session_idb.execute('SELECT pcf_pid, pcf_descr, pcf_ptc, pcf_pfc FROM pcf WHERE pcf_pid IS NOT NULL ORDER BY pcf_pid').fetchall()
#         dp_ed = [(*i[:2], fmt[i[2]][i[3]]) for i in dp]
#         return dp_ed
#     else:
#         raise NotImplementedError


def make_tc_template(ccf_descr, pool_name='LIVE', preamble='cfl.Tcsend_DB', options='', comment=True, add_parcfg=False):
    """

    :param ccf_descr:
    :param pool_name:
    :param preamble:
    :param options:
    :param comment:
    :param add_parcfg:
    :return:
    """
    try:
        cmd, pars = list(get_tc_list(ccf_descr).items())[0]
    except IndexError:
        raise IndexError('"{}" not found in IDB.'.format(ccf_descr))
    # print(tc_template(cmd, pars, pool_name=pool_name, preamble=preamble, options=options, comment=True))
    return tc_template(cmd, pars, pool_name=pool_name, preamble=preamble, options=options, comment=comment, add_parcfg=add_parcfg)


def tc_template(cmd, pars, pool_name='LIVE', preamble='cfl.Tcsend_DB', options='', comment=True, add_parcfg=False):
    """

    :param cmd:
    :param pars:
    :param pool_name:
    :param preamble:
    :param options:
    :param comment:
    :param add_parcfg:
    :return:
    """
    if comment:
        commentstr = "# TC({},{}): {} [{}]\n# {}\n".format(*cmd[3:], cmd[1], cmd[0], cmd[2])
        newline = '\n'
    else:
        commentstr = ''
        newline = ''

    parcfg = ''
    if add_parcfg:
        for par in pars:
            if par[2] == 'E':
                if par[4] is not None:
                    if par[5] == 'E':
                        parval = '"{}"'.format(par[4])
                    elif par[6] == 'H':
                        parval = '0x{}'.format(par[4])
                    else:
                        parval = par[4]
                else:
                    parval = par[4]
                line = '{} = {}  # {}\n'.format(par[0], parval, par[3])
            elif par[2] == 'F':
                line = '# {} = {}  # {} [NOT EDITABLE]\n'.format(par[0], par[4], par[3])
            else:
                line = ''
            parcfg += line

    parstr = ', '.join(parsinfo_to_str(pars))
    if len(parstr) > 0:
        parstr = ', ' + parstr
    exe = "{}('{}'{}, pool_name='{}'{})".format(preamble, cmd[1], parstr, pool_name, options)
    return commentstr + parcfg + exe + newline


def parsinfo_to_str(pars, separator=None):
    """
    Return list of editable parameter names based on get_tc_list info

    :param pars:
    :param separator:
    :return:
    """
    if separator is None:
        return [par[0] for par in pars if par[2] not in ['A', 'F', None]]  # != (None, None)]
    else:
        return [separator.join(par) for par in pars if par[2] not in ['A', 'F', None]]  # != (None, None)]


def on_open_univie_clicked(button):
    """
    Called by all applications, and called by the univie button to set up the starting options

    :param button:
    :return:
    """
    dict = {'editor': start_editor, 'poolmanager': start_pmgr, 'plotter': start_plotter,
            'monitor': start_monitor, 'poolviewer': start_pv}
    dict[button.get_label().split()[1].lower()]()


def about_dialog(parent=None, action=None):
    """
    Called by the Univie Button, option About, pops up the Credits Window

    :param parent: Instance of the calling Gtk Window, for the Gtk.Dialog
    :param action: Simply the calling button
    :return:
    """
    if not parent:
        return

    pics_path = cfg.get('paths', 'ccs')
    pics_path += '/pixmap'

    dialog = Gtk.AboutDialog()
    dialog.set_transient_for(parent)

    dialog.set_program_name('UVIE Central Checkout System')

    dialog.set_copyright('UVIE 08/2022')
    dialog.set_license_type(Gtk.License.MPL_2_0)
    dialog.set_authors(('Marko Mecina', 'Dominik Moeslinger', 'Thanassis Tsiodras', 'Armin Luntzer'))
    dialog.set_version('2.0')
    dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file(os.path.join(pics_path, 'IfA_Logo_48.png')))
    dialog.set_website('https://space.univie.ac.at')
    dialog.set_website_label('space.univie.ac.at')

    dialog.run()
    dialog.destroy()


def change_communication_func(main_instance=None,new_main=None,new_main_nbr=None,application=None,application_nbr=1,parentwin=None):
    """
    Called by the UVIE button, option Communication. Used to change the main_application for each project
    (main_instance), also possible to only change main communication for one application

    :param new_main:The new main_application to be called every time in the future
    :param new_main_nbr: The instance of the new main_application
    :param application:The application to change the main communication for, None if chang for all
    :param application_nbr:The instance of *application*
    :param main_instance:The project in which the changes should apply
    :param parentwin:Instance of a Gtk.Window for the Gtk.Dialog, *None* if called from a command line
    :return:
    """
    save_com = {}
    # Check if a main_instance (project) is given otherwise try to get one, this is a necessary information
    if not main_instance:
        if is_open(application.lower(), application_nbr):
            conn = dbus_connection(application.lower(), application_nbr)
            main_instance = conn.Variables('main_instance')
        else:
            # print('Please give a value for "main_instance" (project name)')
            logger.warning('No main_instance was given therefore main communication could not be changed')
            return
    # Instance from an application is given call the dialog
    if parentwin:
        dialog = ChangeCommunicationDialog(parent=parentwin, cfg=cfg, main_instance=main_instance) # Start Dialog
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            if dialog.change_button.get_active(): #Change for the entire main_instance project
                for conn in dialog.new_communication:
                    change_main_communication(conn, dialog.new_communication[conn], main_instance, parentwin.my_bus_name)
            else:   # Change only for the calling application
                communication = dialog.new_communication

        dialog.destroy()
    # Change the main communication for one application
    elif new_main and new_main_nbr and application and application_nbr:
        if is_open(application.lower(), application_nbr) and is_open(new_main.lower(), new_main_nbr):
            conn = dbus_connection(application.lower(), application_nbr)
            conn.Functions('change_communication', application.lower(), application_nbr)
        else:
            # print('Given application instance or new main communication instance is not open')
            logger.warning('Could not change main communication instance to {} for {} since one of these is not '
                        'running'.format(str(new_main)+str(new_main_nbr), str(application)+str(application_nbr)))
    # Change the main communication for the entire project
    elif new_main and new_main_nbr:
        change_main_communication(new_main, new_main_nbr, main_instance)
    else:
        # print('Please give a new main application and the instance number')
        logger.warning('Not enough information was given to change the main communication')

    return


def change_main_communication(new_main, new_main_nbr, main_instance, own_bus_name=None):
    """
    Changes the main_communication for the entire main_instance (project)

    :param new_main: The new main_application to be called every time in the future
    :param new_main_nbr: The instance of the new main_application
    :param main_instance: The application to change the main communication for, None if chang for all
    :param own_bus_name: The instance of :param application
    :return:
    """
    # Change all communication to the new main
    for service in dbus.SessionBus().list_names(): # Check all running dbus clients
        #print(cfg['ccs-dbus_names'])
        if service[:-1] in cfg['ccs-dbus_names'].values():  # Filter running for the CCS
            if service == own_bus_name:     # If it is the calling application dbus can not be used, simply change
                communication[new_main] = new_main_nbr
                continue
            # For the rest in the same project do the change via dbus
            conn = dbus_connection(service.split('.')[1], service[-1])
            if conn.Variables('main_instance') == main_instance:
                conn.Functions('change_communication', new_main, int(new_main_nbr), False)

    return


def add_decode_parameter(parentwin=None):  # , label=None, fmt=None, bytepos=None):
    """
    Add a parameter which can be used in a User DEFined packet, only defined by the format and can therefore only be
    used if the package is decoded in the given order

    :param parentwin: For graphical usage
    :return:
    """

    if parentwin is not None:
        dialog = TmParameterDecoderDialog(parent=parentwin)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            label = dialog.label.get_text()
            fmt = dialog.format.get_active_text()
            if fmt in fmtlist:
                fmt = fmtlist[fmt]
                if fmt in ('uint', 'ascii', 'oct'):
                    fmt += str(dialog.bitlen.get_text())

            else:
                fmt += str(dialog.bitlen.get_text())
                fmt = fmt.replace('*', '')
                if fmt.upper() in fmtlist:
                    fmt = fmtlist[fmt.upper()]
            dialog.destroy()
        else:
            dialog.destroy()
            return

    else:
        logger.error('Please give a valid format')
        return

    cfg.save_option_to_file('ccs-decode_parameters', label, json.dumps({'format': str(fmt)}))

    if fmt:
        return {'format': str(fmt)}
    else:
        return


def add_tm_decoder(label=None, st=None, sst=None, apid=None, sid=None, parameters=None, parentwin=None):
    """
    Add User DEFined packet with decoding info for TM not defined in IDB

    :param label: Name of new defined packet
    :param st: Service Type
    :param sst: Sub Service Type
    :param apid:
    :param sid:
    :param parameters: list of parameters
    :param parentwin:
    :return:
    """

    if label and st and sst and apid:
        sid = sid if sid else 0
        tag = '{}-{}-{}-{}'.format(st, sst, apid, sid)

    elif parentwin is not None:
        dialog = TmDecoderDialog(logger=logger, parent=parentwin)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            parameters = [par for par in dialog.parameter_list]
            sid = dialog.sid.get_text() if dialog.sid.get_text() else 0
            tag = '{}-{}-{}-{}'.format(dialog.st.get_text(), dialog.sst.get_text(), dialog.apid.get_text(), sid)
            label = dialog.label.get_text()
            dialog.destroy()
        else:
            dialog.destroy()
            return
    else:
        logger.error('Please give: label, st, sst and apid')
        return

    if not parameters:
        logger.warning('No parameters given, cannot create custom TM')
        return

    params = [_parameter_decoding_info(par, check_curtx=True) for par in parameters]
    logger.debug('Created custom TM decoder {} with parameters: {}'.format(label, [x[1] for x in params]))
    user_tm_decoders[tag] = (label, params)

    if not cfg.has_section('ccs-user_defined_packets'):
        cfg.add_section('ccs-user_defined_packets')
    cfg.save_option_to_file('ccs-user_defined_packets', tag, json.dumps((label, [tuple(x) for x in params])))

    return label


def _parameter_decoding_info(param, check_curtx=False):
    """
    Return parameter info tuple used for TM decoding

    :param param:
    :return:
    """

    if param[1] not in ['user_defined', 'user_defined_nopos', 'dp_item']:
        que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx,pcf.pcf_width,pcf.pcf_unit,' \
              'pcf.pcf_pid,null,null,null from pcf WHERE pcf_name ="{}"'.format(param[1])
        dinfo = scoped_session_idb.execute(que).fetchall()[0]

    elif param[1] == 'user_defined':
        fmt = json.loads(cfg[CFG_SECT_PLOT_PARAMETERS][param[0]])['format']
        ptc, pfc = ptt_reverse(fmt)
        dinfo = [param[1], param[0], ptc, pfc, None, csize(fmt) * 8, None, None, None, None, None]

    elif param[1] == 'user_defined_nopos':
        fmt = json.loads(cfg[CFG_SECT_DECODE_PARAMETERS][param[0]])['format']
        ptc, pfc = ptt_reverse(fmt)
        dinfo = [param[1], param[0], ptc, pfc, None, csize(fmt) * 8, None, None, None, None, None]

    elif param[1] == 'dp_item':
        if isinstance(param[0], int):
            dp_id = param[0]
            dp_descr = DP_IDS_TO_ITEMS[param[0]]
        else:
            dp_id = DP_ITEMS_TO_IDS[param[0].split(' ')[0]]  # strip IDs in parentheses if present from parameter dialog model
            dp_descr = DP_IDS_TO_ITEMS[dp_id]

        if check_curtx:
            try:
                que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx,pcf.pcf_width,pcf.pcf_unit,' \
                      'pcf.pcf_pid,null,null,null from pcf WHERE pcf_pid ="{}"'.format(dp_id)
                dinfo = scoped_session_idb.execute(que).fetchall()[0]
                return dinfo
            except IndexError:
                logger.debug('PID {} not in MIB.'.format(dp_id))

        ptc, pfc = ptt_reverse(_dp_items[dp_id]['fmt'])
        dinfo = [param[1], dp_descr, ptc, pfc, None, csize(_dp_items[dp_id]['fmt']) * 8, None, None, None, None, None]

    else:
        logger.warning('Info for parameter "{}" cannot be obtained'.format(param[0]))
        dinfo = None

    return dinfo


def create_hk_decoder(sid, *dp_ids, apid=None):
    """
    Create a decoder to interpret custom HK packets not defined in the MIB

    :param sid: SID of the custom HK
    :param dp_ids: list of parameters in the custom HK
    :param apid: APID of the custom HK packet
    :return:

    """
    parameters = [(dp_id, 'dp_item') for dp_id in dp_ids]

    if apid is None:
        que = 'SELECT pic_apid FROM pic WHERE pic_type=3 AND pic_stype=25'
        res = scoped_session_idb.execute(que).fetchall()
        apid = int(res[0][0])


    sid_off, sid_width = SID_LUT[(3, 25, apid)]

    que = 'SELECT plf_name, pcf_descr FROM pid left join plf on PLF_SPID=PID_SPID left join pcf on ' \
                'PCF_NAME=PLF_NAME where PID_TYPE=3 and PID_STYPE=25 and PID_APID={} and plf_offby={}'.format(apid, sid_off)
    sid_name, sid_descr = scoped_session_idb.execute(que).fetchall()[0]

    if sid_off != TM_HEADER_LEN:
        logger.warning('Inconsistent definition of SID parameter')

    parameters = [(sid_descr, sid_name)] + parameters
    label = add_tm_decoder(label='HK_{}'.format(sid), st=3, sst=25, apid=apid, parameters=parameters, sid=sid)
    return label


def add_user_parameter(parameter=None, apid=None, st=None, sst=None, sid=None, bytepos=None, fmt=None, offbi=None,
                       bitlen=None, parentwin=None):
    """
    Add a stand-alone (i.e. with positional info) User DEFined parameter

    :param parameter:
    :param apid:
    :param st:
    :param sst:
    :param sid:
    :param bytepos:
    :param fmt:
    :param offbi:
    :param bitlen:
    :param parentwin:
    :return:
    """
    # If a Gtk Parent Window is given, open the Dialog window to specify the details for the parameter
    if parentwin is not None:
        dialog = UserParameterDialog(parent=parentwin)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            try:
                label = dialog.label.get_text()
                apid = int(dialog.apid.get_text(), 0) if dialog.apid.get_text() != '' else None
                st, sst, sid = int(dialog.st.get_text(), 0), int(dialog.sst.get_text(), 0), dialog.sid.get_text()
                offbi = dialog.offbi.get_text()

                sid = int(sid, 0) if sid != '' else None
                offbi = int(offbi, 0) if offbi != '' else 0

                bytepos, fmt = int(dialog.bytepos.get_text(), 0), fmtlist[dialog.format.get_active_text()]
                if fmt in ('uint', 'ascii', 'oct'):
                    fmt += dialog.bitlen.get_text()
            except Exception as err:
                logger.error(err)
                dialog.destroy()
                return None

            if not cfg.has_section(CFG_SECT_PLOT_PARAMETERS):
                cfg.add_section(CFG_SECT_PLOT_PARAMETERS)
            cfg.save_option_to_file(CFG_SECT_PLOT_PARAMETERS, label, json.dumps(
                {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi}))

            dialog.destroy()
            return label, apid, st, sst, sid, bytepos, fmt, offbi

        dialog.destroy()
        return

    # Else if parameter is given the others have to exist as well and the parameter is created
    if isinstance(parameter, str):
        label = parameter
        if isinstance(apid, int) and isinstance(st, int) and isinstance(sst, int) and isinstance(bytepos, int) and fmt:
            if fmt in ('uint', 'ascii', 'oct'):
                if bitlen:
                    fmt += bitlen
                else:
                    # print('Please give a bitlen (Amount of Bits) if fmt (Parameter Type) is set to "bit"')
                    logger.error('Parameter could not be created, no length was given.')
                    return

            if not isinstance(sid,int):
                sid = int(sid, 0) if sid is not None else None
            if not isinstance(offbi, int):
                offbi = int(offbi, 0) if offbi is not None else 0
        else:
            # print('Please give all neaded parameters in the correct format')
            logger.error('Parameter could not be created, because not all specifications were given correctly')
            return
    # Else if the Parameter is given as a Dictionary get all the needed informations and create the parameter
    elif isinstance(parameter, dict):
        label = parameter['label']
        apid = parameter['apid']
        st = parameter['st']
        sst = parameter['sst']
        byteps = parameter['bytepos']
        fmt = parameter['fmt']
        if isinstance(label, str) and isinstance(apid, int) and isinstance(st, int) and isinstance(sst, int) and isinstance(bytepos, int) and fmt:
            if fmt in ('uint', 'ascii', 'oct'):
                if bitlen:
                    fmt += bitlen
                else:
                    # print('Please give a bitlen (Amount of Bits) if fmt (Parameter Type) is set to "bit"')
                    logger.error('Parameter could not be created, no length was given.')
                    return

            if not isinstance(parameter['sid'], int):
                sid = int(parameter['sid'], 0) if parameter['sid'] else None
            if not isinstance(parameter['offbi'], int):
                offbi = int(parameter['offbi'], 0) if parameter['offbi'] else 0
        else:
            # print('Please give all neaded parameters in the correct format')
            logger.error('Parameter could not be created, because not all specifications were given correctly')
            return

    else:
        logger.error('Please give all arameters correctly')
        return
    # Add the created Parameter to the config file egse.cfg
    if not cfg.has_section(CFG_SECT_PLOT_PARAMETERS):
        cfg.add_section(CFG_SECT_PLOT_PARAMETERS)

    cfg.save_option_to_file(CFG_SECT_PLOT_PARAMETERS, label, json.dumps(
        {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi}))

    return label, apid, st, sst, sid, bytepos, fmt, offbi


# Removes a user defined Parameter
def remove_user_parameter(parname=None, parentwin=None):
    """

    :param parname:
    :param parentwin:
    :return:
    """
    # If a Parameter is given delete the parameter
    if parname and cfg.has_option(CFG_SECT_PLOT_PARAMETERS, parname):
        cfg.remove_option_from_file(CFG_SECT_PLOT_PARAMETERS, parname)

        return parname

    # Else if a Parent Gtk window is given open the dialog to select a parameter
    # elif parentwin is not None:
    #     dialog = RemoveUserParameterDialog(cfg, parentwin)
    #     response = dialog.run()
    #     if response == Gtk.ResponseType.OK:
    #         param = dialog.remove_name.get_active_text()
    #
    #         cfg.remove_option_from_file(CFG_SECT_PLOT_PARAMETERS, param)
    #
    #         return param
    #
    #     else:
    #         dialog.destroy()
    #
    #     return

    elif parname is not None:
        logger.error('Unknown parameter {}. Cannot remove.'.format(parname))


# Edit an existing user defined Parameter
def edit_user_parameter(parentwin=None, parname=None):
    """

    :param parentwin:
    :param parname:
    :return:
    """

    # if an existing parameter is given, open same window as for adding a parameter, but pass along the existing information
    # simply overwrite the existing parameter with the new one
    if parname and cfg.has_option(CFG_SECT_PLOT_PARAMETERS, parname):
        dialog = UserParameterDialog(parentwin, parname)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            try:
                label = dialog.label.get_text()
                apid = int(dialog.apid.get_text(), 0) if dialog.apid.get_text() != '' else None
                st, sst, sid = int(dialog.st.get_text(), 0), int(dialog.sst.get_text(), 0), dialog.sid.get_text()
                offbi = dialog.offbi.get_text()

                sid = int(sid, 0) if sid != '' else None
                offbi = int(offbi, 0) if offbi != '' else 0

                bytepos, fmt = int(dialog.bytepos.get_text(), 0), fmtlist[dialog.format.get_active_text()]
                if fmt in ('uint', 'ascii', 'oct'):
                    fmt += dialog.bitlen.get_text()
            except ValueError as error:
                logger.error(error)
                dialog.destroy()
                return

            if label != parname:
                cfg.remove_option_from_file(CFG_SECT_PLOT_PARAMETERS, parname)

            if not cfg.has_section(CFG_SECT_PLOT_PARAMETERS):
                cfg.add_section(CFG_SECT_PLOT_PARAMETERS)
            cfg.save_option_to_file(CFG_SECT_PLOT_PARAMETERS, label, json.dumps(
                {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi}))

            dialog.destroy()

            return label, apid, st, sst, sid, bytepos, fmt, offbi
        else:
            dialog.destroy()
            return

    # Else Open a Window to select a parameter and call the same function again with an existing parameter
    # The upper code will be executed
    else:
        logger.error('Unknown parameter {}'.format(parname))
        return
        # if parname is not None:
        #     logger.warning('User defined parameter "{}" could not be found, please select a new one'.format(parname))
        #
        # dialog = EditUserParameterDialog(cfg, parentwin)
        # response = dialog.run()
        # if response == Gtk.ResponseType.OK:
        #     param = dialog.edit_name.get_active_text()
        #     dialog.destroy()
        #     ret = edit_user_parameter(parentwin, param)
        #     if ret:
        #         label, apid, st, sst, sid, bytepos, fmt, offbi = ret
        #         return label, apid, st, sst, sid, bytepos, fmt, offbi
        #     else:
        #         return
        # else:
        #     dialog.destroy()
        #     return


def read_plm_gateway_data(raw):
    """
    Interprets raw data from SMILE SXI PLM SpW Gateway data port (5000) and returns SpW packet(s) plus decoded PLM header data (see H8823-UM-HVS-0001)

    :param raw: binary data as received from PLM Gateway
    :return:
    """
    ct, ft, sw, data = raw[:4], raw[4:8], raw[8:12], raw[12:]
    t = int.from_bytes(ct, 'little') + int.from_bytes(ft, 'little') / 1e9
    tatype = bin(sw[-1] & 0b11)
    plen = int.from_bytes(sw[:3], 'little')
    return data, plen, t, tatype


def pack_plm_gateway_data(raw):
    """
    Pack data for TC to SMILE SXI PLM SpW Gateway data port (5000) (see H8823-UM-HVS-0001)

    :param raw: binary SpW packet
    :return:
    """
    cw = len(raw).to_bytes(3, 'little') + b'\x00'  # command word for EOP terminated packet
    return cw + raw


def get_spw_from_plm_gw(sock_plm, sock_gnd, strip_spw=4):
    """

    :param sock_plm:
    :param sock_gnd:
    :param strip_spw:
    """
    # print('> SPW PCKT routing started! <')
    # while sock_plm.fileno() > 0 and sock_gnd.fileno() > 0:

    data = b''
    while len(data) < 12:
        data += sock_plm.recv(12 - len(data))

    spwdata, plen, _, _ = read_plm_gateway_data(data)
    while len(spwdata) < plen:
        spwdata += sock_plm.recv(plen - len(spwdata))

    if strip_spw:
        sock_gnd.send(spwdata[strip_spw:])  # strip SpW header before routing packet
    else:
        sock_gnd.send(spwdata)
    logger.info(plen, len(spwdata), spwdata.hex())


def setup_gw_spw_routing(gw_hp, gnd_hp, tc_hp=None, spw_head=b'\xfe\x02\x00\x00'):
    """
    A router for the single-port HVS SpW Brick that handles the HVS and SpW protocol for the CCS

    :param gw_hp:
    :param gnd_hp:
    :param tc_hp:
    :param spw_head:
    """
    gw = socket.socket()
    gw.settimeout(10)
    gw.connect(gw_hp)

    gnd = socket.socket()
    gnd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    gnd.bind(gnd_hp)
    gnd.listen()

    if tc_hp is not None:
        tcsock = socket.socket()
        tcsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcsock.bind(tc_hp)
        tcsock.listen()
    else:
        tcsock = gnd

    while gw.fileno() > 0:
        logger.info(gw, gnd)
        gnd_s, addr = gnd.accept()
        tc_s, addr2 = tcsock.accept()

        while True:
            try:
                r, w, e = select.select([gw, tc_s], [], [])
                for sockfd in r:
                    if sockfd == gw:
                        while select.select([gw], [], [], 0)[0]:
                            get_spw_from_plm_gw(gw, gnd_s, strip_spw=len(spw_head))
                    elif sockfd == tc_s:
                        while select.select([tc_s], [], [], 0)[0]:
                            rawtc = tc_s.recv(1024)
                            if rawtc == b'':
                                raise socket.error('Lost connection to port '.format(tc_s.getsockname()))
                            else:
                                logger.info('# TC:', spw_head + rawtc)
                                msg = pack_plm_gateway_data(spw_head + rawtc)
                                gw.send(msg)

            # t_tc = threading.Thread(target=get_spw_from_plm_gw, args=[gw, tc_s])

            except socket.timeout:
                continue
            except socket.error:
                gnd_s.close()
                tc_s.close()
                logger.info('Closed TM/TC ports. Reopening...')
                break

        time.sleep(1)

    gnd.close()
    tcsock.close()
    gw.close()


def _gresb_unpack(raw, hdr_endianess='big'):
    pid = raw[0]
    pktlen = int.from_bytes(raw[1:4], hdr_endianess)
    return raw[4:], pktlen, pid


def _gresb_pack(pkt, protocol_id=0, hdr_endianess='big'):
    return protocol_id.to_bytes(1, hdr_endianess) + len(pkt).to_bytes(3, hdr_endianess) + pkt


def get_gresb_pkt(gresb, gnd_s, hdr_endianess='big'):
    """

    :param gresb:
    :param gnd_s:
    :param hdr_endianess:
    """
    data = b''
    while len(data) < 4:
        data += gresb.recv(4 - len(data))

    spwdata, plen, pid = _gresb_unpack(data, hdr_endianess=hdr_endianess)
    while len(spwdata) < plen:
        spwdata += gresb.recv(plen - len(spwdata))

    gnd_s.send(spwdata)

    logger.debug(plen, len(spwdata), spwdata.hex())
    print(plen, len(spwdata), spwdata.hex())


def setup_gresb_routing(gresb_hp, gnd_hp, tc_hp=None, protocol_id=0, hdr_endianess='big'):
    """
    Handle GRESB protocol for CCS

    :param gresb_hp:
    :param gnd_hp:
    :param tc_hp:
    :param protocol_id:
    :param hdr_endianess:
    """
    gresb = socket.socket()
    gresb.settimeout(10)
    gresb.connect(gresb_hp)

    gnd = socket.socket()
    gnd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    gnd.bind(gnd_hp)
    gnd.listen()

    if tc_hp is not None:
        tcsock = socket.socket()
        tcsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcsock.bind(tc_hp)
        tcsock.listen()
    else:
        tcsock = gnd

    while gresb.fileno() > 0:
        logger.info(gresb, gnd)
        gnd_s, addr = gnd.accept()
        tc_s, addr2 = tcsock.accept()

        while True:
            try:
                print('START')
                r, w, e = select.select([gresb, tc_s], [], [])
                print(r)
                for sockfd in r:
                    if sockfd == gresb:
                        while select.select([gresb], [], [], 0)[0]:
                            get_gresb_pkt(gresb, gnd_s, hdr_endianess=hdr_endianess)
                    elif sockfd == tc_s:
                        while select.select([tc_s], [], [], 0)[0]:
                            rawtc = tc_s.recv(1024)
                            if rawtc == b'':
                                raise socket.error('Lost connection to port '.format(tc_s.getsockname()))
                            else:
                                logger.info('# TC:', rawtc)
                                print('# TC:', rawtc)
                                msg = _gresb_pack(rawtc, protocol_id=protocol_id, hdr_endianess=hdr_endianess)
                                print(gresb)
                                gresb.send(msg)
                                print(msg)

            except socket.timeout:
                continue
            except socket.error:
                gnd_s.close()
                tc_s.close()
                logger.info('Closed TM/TC ports. Reopening...')
                break
            print('########')
        time.sleep(1)

    gnd.close()
    tcsock.close()
    gresb.close()


def extract_spw(stream):
    """
    Read SpW packets from a byte stream

    :param stream:
    :return:
    """

    pkt_size_stream = b''
    pckts = []
    headers = []

    while True:
        pkt_size_stream += stream.read(2)
        if len(pkt_size_stream) < 2:
            break
        tla, pid = pkt_size_stream[:2]
        logger.debug('{}, {}'.format(tla, pid))

        # if (tla == pc.SPW_DPU_LOGICAL_ADDRESS) and (pid in SPW_PROTOCOL_IDS_R):
        if pid in SPW_PROTOCOL_IDS_R:
            buf = pkt_size_stream
        else:
            pkt_size_stream = pkt_size_stream[1:]
            continue

        if SPW_PROTOCOL_IDS_R[pid] == "FEEDATA":
            header = pc.FeeDataTransferHeader()
        elif SPW_PROTOCOL_IDS_R[pid] == "RMAP":
            while len(buf) < 3:
                instruction = stream.read(1)
                if not instruction:
                    return pckts, buf
                buf += instruction

            instruction = buf[2]

            if (instruction >> 6) & 1:
                header = pc.RMapCommandHeader()
            elif (instruction >> 5) & 0b11 == 0b01:
                header = pc.RMapReplyWriteHeader()
            elif (instruction >> 5) & 0b11 == 0b00:
                header = pc.RMapReplyReadHeader()

        hsize = header.__class__.bits.size

        while len(buf) < hsize:
            buf += stream.read(hsize - len(buf))

        header.bin[:] = buf[:hsize]

        if SPW_PROTOCOL_IDS_R[pid] == "FEEDATA":
            pktsize = header.bits.DATA_LEN
        elif (header.bits.PKT_TYPE == 1 and header.bits.WRITE == 0) or (
                header.bits.PKT_TYPE == 0 and header.bits.WRITE == 1):
            pktsize = hsize
        else:
            pktsize = hsize + header.bits.DATA_LEN + pc.RMAP_PEC_LEN  # TODO: no data CRC from FEEsim?

        while len(buf) < pktsize:
            data = stream.read(pktsize - len(buf))
            if not data:
                return headers, pckts, pkt_size_stream
            buf += data

        buf = buf[:pktsize]
        pkt_size_stream = buf[pktsize:]
        pckts.append(buf)
        headers.append(header)

    return headers, pckts, pkt_size_stream


##
#  Save pool
#
#  Dump content of data pool _pname_ to file _fname_, either as a concatenated binary sequence or in hexadecimal
#  representation and one packet per line. Selective saving (by service type) possible.
#  @param fname     File name for the dump
#  @param pname     Name of pool to be saved
#  @param mode      Type of the saved file. _binary_ or _hex_
#  @param st_filter Packets of that service type will be saved
def savepool(filename, pool_name, mode='binary', st_filter=None):
    """

    :param filename:
    :param pool_name:
    :param mode:
    :param st_filter:
    """
    # get new session for saving process
    logger.info('Saving pool content to disk...')
    tmlist = list(get_packets_from_pool(pool_name))

    Tmdump(filename, tmlist, mode=mode, st_filter=st_filter, check_crc=False)
    logger.info('Pool {} saved as {} in {} mode'.format(pool_name, filename, mode.upper()))


def get_packets_from_pool(pool_name, indices=None, st=None, sst=None, apid=None, **kwargs):
    """

    :param pool_name:
    :param indices:
    :param st:
    :param sst:
    :param apid:
    :return:
    """
    new_session = scoped_session_storage

    rows = new_session.query(
        DbTelemetry
    ).join(
        DbTelemetryPool,
        DbTelemetry.pool_id == DbTelemetryPool.iid
    ).filter(
        DbTelemetryPool.pool_name == pool_name
    )

    if indices is not None and len(indices) > 0:
        rows = rows.filter(
            DbTelemetry.idx.in_(indices)
        )

    if st is not None:
        rows = rows.filter(DbTelemetry.stc == st)
    if sst is not None:
        rows = rows.filter(DbTelemetry.sst == sst)
    if apid is not None:
        rows = rows.filter(DbTelemetry.apid == apid)

    ret = [row.raw for row in rows.yield_per(1000)]
    new_session.close()
    return ret


def add_tst_import_paths():
    """
    Include all paths to TST files that could potentially be used.

    :return:
    """
    # Add general tst path
    sys.path.append(cfg.get('paths', 'tst'))
    # Add all subfolders
    sys.path.append(cfg.get('paths', 'tst') + '/codeblockreusefeature')
    sys.path.append(cfg.get('paths', 'tst') + '/config_editor')
    sys.path.append(cfg.get('paths', 'tst') + '/confignator')
    sys.path.append(cfg.get('paths', 'tst') + '/doc')
    sys.path.append(cfg.get('paths', 'tst') + '/icon_univie')
    sys.path.append(cfg.get('paths', 'tst') + '/images')
    sys.path.append(cfg.get('paths', 'tst') + '/log_viewer')
    sys.path.append(cfg.get('paths', 'tst') + '/notes')
    sys.path.append(cfg.get('paths', 'tst') + '/progress_view')
    sys.path.append(cfg.get('paths', 'tst') + '/sketch_desk')
    sys.path.append(cfg.get('paths', 'tst') + '/test_specs')
    sys.path.append(cfg.get('paths', 'tst') + '/testing_library')
    sys.path.append(cfg.get('paths', 'tst') + '/testing_library/testlib')
    # insert this to import the tst view.py, not the one in .local folder
    sys.path.insert(0, cfg.get('paths', 'tst') + '/tst')


def interleave_lists(*args):
    """

    :param args:
    :return:
    """
    if len({len(x) for x in args}) > 1:
        logger.warning('Iterables are not of the same length, result will be truncated to the shortest input!')
    return [i for j in zip(*args) for i in j]


def create_format_model():
    """

    :return:
    """
    store = Gtk.ListStore(str)
    for fmt in fmtlist.keys():
        if fmt != 'bit*':
            store.append([fmt])
    for pers in personal_fmtlist:
        store.append([pers])
    return store


def _get_displayed_pool_path(pool_name=None):
    """
    Try to get name of pool currently displayed in poolviewer or loaded in current poolmanager session

    :param pool_name:
    :return:
    """

    if pool_name is None:
        pv = get_module_handle('poolviewer', timeout=1)

        if not pv:
            return

        return str(pv.Variables('active_pool_info')[0])

    pmgr = get_module_handle('poolmanager', timeout=1)
    if not pmgr:
        return

    pools = pmgr.Dictionaries('loaded_pools')
    if pool_name in pools:
        return str(pools[pool_name][0])
    else:
        return


def collect_13(pool_name, starttime=None, endtime=None, startidx=None, endidx=None, join=True, collect_all=False,
               sdu=None, verbose=True, consistency_check=True):
    """
    Collect and group S13 down transfer packet trains

    :param pool_name:
    :param starttime:
    :param endtime:
    :param startidx:
    :param endidx:
    :param join:
    :param collect_all:
    :param sdu:
    :param verbose:
    :param consistency_check:
    :return:
    """

    if not os.path.isfile(pool_name):
        logger.debug('{} is not a file, looking it up in DB'.format(pool_name))
        # try fetching pool info from pools opened in viewer
        # pname = _get_displayed_pool_path(pool_name)
        # if pname:
        #     pool_name = pname

    rows = get_pool_rows(pool_name, check_existence=True)

    # faster method to collect already completed TM13 transfers
    tm_bounds = rows.filter(DbTelemetry.stc == 13, DbTelemetry.sst.in_([1, 3, 4])).order_by(DbTelemetry.idx)

    if starttime is not None:
        tm_bounds = tm_bounds.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) >= starttime)

    if endtime is not None:
        tm_bounds = tm_bounds.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) <= endtime)

    if startidx is not None:
        tm_bounds = tm_bounds.filter(DbTelemetry.idx >= startidx)

    if endidx is not None:
        tm_bounds = tm_bounds.filter(DbTelemetry.idx <= endidx)

    if sdu:
        tm_bounds = tm_bounds.filter(func.left(DbTelemetry.data, 1) == sdu.to_bytes(SDU_PAR_LENGTH, 'big'))

    # quit if no start packet is found
    if tm_bounds.filter(DbTelemetry.sst == 1).count() == 0:
        return {None: None}

    tm_132 = rows.filter(DbTelemetry.stc == 13, DbTelemetry.sst == 2).order_by(DbTelemetry.idx)

    if starttime is not None:
        tm_132 = tm_132.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) >= starttime)

    if endtime is not None:
        tm_132 = tm_132.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) <= endtime)

    if startidx is not None:
        tm_132 = tm_132.filter(DbTelemetry.idx >= startidx)

    if endidx is not None:
        tm_132 = tm_132.filter(DbTelemetry.idx <= endidx)

    if sdu:
        tm_132 = tm_132.filter(func.left(DbTelemetry.data, 1) == sdu.to_bytes(SDU_PAR_LENGTH, 'big'))

    # remove incomplete transfers
    clean_bounds = _check_s13_downlinks(tm_bounds, tm_132)

    if len(clean_bounds) == 0:
        return {None: None}

    if not collect_all:
        clean_bounds = [clean_bounds[0]]

    ces = _assemble_s13(clean_bounds, tm_132, join=join, consistency_check=consistency_check, verbose=verbose)

    return ces


def _check_s13_downlinks(s13_bounds, s13_intermediate):
    """
    Filter out TM13 1 & 3/4 packets from incomplete transfers

    :param s13_bounds:
    :param s13_intermediate:
    :return:
    """

    tx = False
    sidx = 0

    valid_start = None

    clean_transfers = []

    for pkt in s13_bounds:

        if not tx and pkt.sst == 1:
            tx = True
            sidx = pkt.idx
            valid_start = pkt

        elif pkt.sst == 1:
            if s13_intermediate.filter(DbTelemetry.idx > sidx, DbTelemetry.idx < pkt.idx).count():
                logger.warning('incomplete downlink at {}'.format(sidx))
                sidx = pkt.idx
            else:
                clean_transfers.append((valid_start, None))
                logger.debug('single packet downlink at {}'.format(valid_start.idx))
            valid_start = pkt
            tx = True

        elif tx and pkt.sst == 3:
            clean_transfers.append((valid_start, pkt))
            valid_start = None
            tx = False

        elif not tx and pkt.sst == 3:
            tx = False
            logger.debug('unexpected end-of-transmission packet at {}'.format(pkt.idx))

        elif tx and pkt.sst == 4:
            tx = False
            logger.warning('aborted downlink at {}'.format(pkt.idx))

        elif not tx and pkt.sst == 4:
            tx = False
            logger.warning('unexpected abort-of-transmission packet at {}'.format(pkt.idx))

        else:
            logger.error("I shouldn't be here! ({})".format(pkt.idx))

    return clean_transfers


def _assemble_s13(bounds, tm_132, join=True, consistency_check=False, verbose=True):
    """
    Assemble payload data from S13 transfers.

    :param bounds:
    :param tm_132:
    :param join:
    :param consistency_check:
    :param verbose:
    :return:
    """

    ces = {}
    errs = []

    scnt_offset = TM_HEADER_LEN + _s13_info[0][1]
    scnt_size = _s13_info[1][1]

    for i, j in bounds:

        try:
            # single packet transfer
            if j is None:
                firstpktdata = b''
                pkts = []
                datalen = int.from_bytes(i.raw[S13_DATALEN_PAR_OFFSET:S13_DATALEN_PAR_OFFSET + S13_DATALEN_PAR_SIZE], 'big')
                lastpktdata = i.raw[S13_HEADER_LEN_TOTAL:S13_HEADER_LEN_TOTAL + datalen]

            else:
                firstpktdata = i.raw[S13_HEADER_LEN_TOTAL:-PEC_LEN]
                pkts = [a.raw[S13_HEADER_LEN_TOTAL:-PEC_LEN] for a in tm_132.filter(DbTelemetry.idx > i.idx, DbTelemetry.idx < j.idx)]

                # check for padding bytes in last packet
                datalen = int.from_bytes(j.raw[S13_DATALEN_PAR_OFFSET:S13_DATALEN_PAR_OFFSET + S13_DATALEN_PAR_SIZE], 'big')
                lastpktdata = j.raw[S13_HEADER_LEN_TOTAL:S13_HEADER_LEN_TOTAL + datalen]

                if consistency_check:
                    # check if number of collected packets matches the sequence counter of TM13,3
                    cnt = int.from_bytes(j.raw[scnt_offset:scnt_offset + scnt_size], 'big')
                    npkts = len(pkts) + 2
                    if cnt != npkts:
                        logger.warning('Inconsistent number of packets in transfer starting at {}'.format(i.timestamp))
                        errs.append(i.timestamp)

            if join:
                ces[float(i.timestamp[:-1])] = firstpktdata + b''.join(pkts) + lastpktdata
            else:
                ces[float(i.timestamp[:-1])] = [firstpktdata] + pkts + [lastpktdata]

        except Exception as err:
            logger.error(err)

    if verbose:
        print('Collected {} S13 transfers.'.format(len(ces)))
        if len(errs) != 0:
            print('There are inconsistencies in {} transfer(s)!\n{}'.format(len(errs), '\n'.join(errs)))

    return ces


def dump_large_data(pool_name, starttime=0, endtime=None, outdir="", dump_all=False, sdu=None, startidx=None,
                    endidx=None, verbose=True, consistency_check=True):
    """
    Dump S13 down transfer data to disk. For pools loaded from a file, pool_name must be the absolute path of that file.

    :param pool_name:
    :param starttime:
    :param endtime:
    :param outdir:
    :param dump_all:
    :param sdu:
    :param startidx:
    :param endidx:
    :param verbose:
    :param consistency_check:
    """

    if not os.path.exists(outdir):
        raise FileNotFoundError('Directory "{}" does not exist'.format(outdir))

    filedict = {}
    ldt_dict = collect_13(pool_name, starttime=starttime, endtime=endtime, join=True, collect_all=dump_all,
                          startidx=startidx, endidx=endidx, sdu=sdu, verbose=verbose, consistency_check=consistency_check)

    ldt_cnt = 0
    for buf in ldt_dict:
        if ldt_dict[buf] is None:
            continue

        try:
            obsid, ctime, ftime, ctr = s13_unpack_data_header(ldt_dict[buf])
        except NotImplementedError:
            obsid = int(datetime.datetime.utcnow().strftime('%j'))
            ctime = int(buf)
            ftime = 0
            ctr = crc(ldt_dict[buf])
        except ValueError as err:
            logger.error('Incompatible definition of S13 data header.')
            raise err

        fname = os.path.join(outdir, "LDT_{:03d}_{:010d}_{:06d}.ce".format(obsid, ctime, ctr))

        with open(fname, "wb") as fdesc:
            fdesc.write(ldt_dict[buf])
            filedict[buf] = fdesc.name
            ldt_cnt += 1

    if ldt_cnt != 0:
        logger.info('Dumped {} CEs to {}'.format(ldt_cnt, outdir))
    logger.debug('{} CEs found'.format(ldt_cnt))
    # print('Dumped {} CEs to {}'.format(ldt_cnt, outdir))

    return filedict


def get_hk_def_tcs(filename, sid=None, sidoff=TC_HEADER_LEN, sidbs=2):
    """
    Search binary pool dump for HK definitions (TC(3,1))

    @param filename:
    @param sid: Only return HK definitions with this SID if not None
    @param sidoff:
    @param sidbs:
    @return:
    """

    with open(filename, 'rb') as fd:
        pkts = extract_pus(fd)

    if sid is None:
        pkts = [pkt for pkt in pkts if (pkt[7] == 3) and (pkt[8] == 1)]
    else:
        pkts = [pkt for pkt in pkts if (pkt[7] == 3) and (pkt[8] == 1) and (int.from_bytes(pkt[sidoff:sidoff+sidbs], 'big') == sid)]

    return pkts


class DbTools:
    """
    SQL database management tools
    """

    @staticmethod
    def recover_from_db(pool_name=None, iid=None, dump=False):
        """
        Recover TMTC packets not stored on disk from DB
        @param pool_name:
        @param iid:
        @param dump:
        @return:
        """
        new_session = scoped_session_storage
        if pool_name:
            rows = new_session.query(
                DbTelemetry).join(
                DbTelemetryPool, DbTelemetry.pool_id == DbTelemetryPool.iid).filter(
                DbTelemetryPool.pool_name == pool_name)
        elif iid:
            rows = new_session.query(
                DbTelemetry).join(
                DbTelemetryPool, DbTelemetry.pool_id == DbTelemetryPool.iid).filter(
                DbTelemetryPool.iid == iid)
        else:
            logger.error('Must give pool_name or iid')
            return None

        if dump:
            with open(dump, 'wb') as fdesc:
                fdesc.write(b''.join([row.raw for row in rows]))
        new_session.close()
        return rows

    @staticmethod
    def clear_from_db(pool_name, answer=''):
        """
        Remove pool pool_name from DB
        @param pool_name:
        @param answer:
        @return:
        """
        # answer = ''
        while answer.lower() not in ['yes', 'no', 'y', 'n']:
            answer = input("Clear pool\n >{}<\nfrom DB? (yes/no)\n".format(pool_name))
        if answer.lower() in ['yes', 'y']:
            new_session = scoped_session_storage
            indb = new_session.execute('select * from tm_pool where pool_name="{}"'.format(pool_name))
            if len(indb.fetchall()) == 0:
                logger.error('POOL\n >{}<\nNOT IN DB!'.format(pool_name))
                return
            new_session.execute(
                'delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid where tm_pool.pool_name="{}"'.format(
                    pool_name))
            new_session.execute('delete tm_pool from tm_pool where tm_pool.pool_name="{}"'.format(pool_name))
            # new_session.flush()
            new_session.commit()
            new_session.close()
            logger.info('DELETED POOL\n >{}<\nFROM DB'.format(pool_name))
        return

    @staticmethod
    def _clear_db():
        """
        Delete all pools from DB
        @return:
        """
        answer = ''
        while answer.lower() not in ['yes', 'no', 'y', 'n']:
            answer = input(" > > > Clear all TMTC data from DB? < < < (yes/no)\n".upper())
        if answer.lower() in ['yes', 'y']:
            new_session = scoped_session_storage
            new_session.execute('delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid')
            new_session.execute('delete tm_pool from tm_pool')
            # new_session.flush()
            new_session.commit()
            new_session.close()
            logger.info('>>> DELETED ALL POOLS FROM DB <<<')
        return

    @staticmethod
    def _purge_db_logs(date=None):
        """
        Purge binary MySQL logs before _date_
        @param date: ISO formatted date string; defaults to now, if None
        """
        if date is None:
            now = datetime.datetime.now()
            date = datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')
        new_session = scoped_session_storage
        new_session.execute('PURGE BINARY LOGS BEFORE "{:s}"'.format(date))
        new_session.close()

    @staticmethod
    def delete_abandoned_rows(timestamp=None):
        new_session = scoped_session_storage
        try:
            if timestamp is None:
                new_session.execute(
                    'DELETE tm FROM tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
                new_session.execute(
                    'DELETE rmap_tm FROM rmap_tm INNER JOIN tm_pool ON rmap_tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
                new_session.execute(
                    'DELETE feedata_tm FROM feedata_tm INNER JOIN tm_pool ON feedata_tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
                new_session.execute('DELETE tm_pool FROM tm_pool WHERE tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
            else:
                new_session.execute(
                    'DELETE tm FROM tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name="---TO-BE-DELETED{}"'.format(timestamp))
                new_session.execute('DELETE tm_pool FROM tm_pool WHERE tm_pool.pool_name="---TO-BE-DELETED{}"'.format(
                    timestamp))

            new_session.commit()
            return 0
        except Exception as err:
            logger.error("Error trying to delete old DB rows: {}".format(err))
            new_session.rollback()
            return 1
        finally:
            new_session.close()

    @staticmethod
    def sql_insert_binary_dump(filename, brute=False, force_db_import=False, protocol='PUS', pecmode='warn', parent=None):

        active_pool_info = ActivePoolInfo(
            filename,
            int(os.path.getmtime(filename)),
            os.path.basename(filename),
            False)

        new_session = scoped_session_storage()
        filename_in_pool = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == active_pool_info.filename)

        pool_exists_in_db_already = filename_in_pool.filter(DbTelemetryPool.modification_time == active_pool_info.modification_time).count() > 0

        if (not pool_exists_in_db_already) or force_db_import:
            if force_db_import or filename_in_pool.count():
                del_time = time.strftime('%s')
                new_session.execute(
                    'UPDATE tm_pool SET pool_name="---TO-BE-DELETED{}" WHERE tm_pool.pool_name="{}"'.format(
                        del_time, filename))
                new_session.commit()
                new_session.close()
                # delete obsolete rows
                del_thread = threading.Thread(target=DbTools.delete_abandoned_rows, args=[del_time], name='delete_abandoned')
                del_thread.daemon = True
                del_thread.start()

            logger.info("Data not in DB - must import...")
            loadinfo = LoadInfo(parent=parent)
            # loadinfo.spinner.start()
            # loadinfo.show_all()
            new_session.close()

            _loader_thread = threading.Thread(target=DbTools.import_dump_in_db,
                                              args=[active_pool_info, loadinfo],
                                              kwargs={'brute': brute, 'protocol': protocol, 'pecmode': pecmode})
            _loader_thread.daemon = True
            _loader_thread.start()

            logger.info('Loading Pool: ' + str(filename))

        else:
            _loader_thread = None
            new_session.close()

        # logger.info('Loaded Pool:' + str(filename))

        return active_pool_info, _loader_thread

    @staticmethod
    def import_dump_in_db(pool_info, loadinfo, brute=False, protocol='PUS', pecmode='warn'):

        loadinfo.ok_button.set_sensitive(False)
        loadinfo.spinner.start()
        new_session = scoped_session_storage

        try:
            new_session.query(
                DbTelemetryPool
            ).filter(
                DbTelemetryPool.pool_name == pool_info.filename
            ).delete()
            new_session.flush()
            newPoolRow = DbTelemetryPool(
                pool_name=pool_info.filename,
                modification_time=pool_info.modification_time,
                protocol=protocol)
            new_session.add(newPoolRow)
            new_session.flush()  # DB assigns auto-increment field (primary key iid) used below
        except Exception as err:
            new_session.rollback()
            new_session.close()
            raise err

        bulk_insert_size = 1000  # number of rows to transfer in one transaction
        state = [1]
        protocol_ids = SPW_PROTOCOL_IDS_R

        def mkdict_spw(head, tm_raw):
            pkt = head.bits

            if protocol_ids[pkt.PROTOCOL_ID] == 'RMAP':
                pcktdict = dict(pool_id=newPoolRow.iid,
                                idx=state[0],
                                cmd=pkt.PKT_TYPE,
                                write=pkt.WRITE,
                                verify=pkt.VERIFY,
                                reply=pkt.REPLY,
                                increment=pkt.INCREMENT,
                                keystat=pkt.KEY if pkt.PKT_TYPE == 1 else pkt.STATUS,
                                taid=pkt.TRANSACTION_ID,
                                addr=pkt.ADDR if pkt.PKT_TYPE == 1 else None,
                                datalen=pkt.DATA_LEN if hasattr(pkt, 'DATA_LEN') else 0,
                                raw=tm_raw)

            elif protocol_ids[pkt.PROTOCOL_ID] == 'FEEDATA':
                pcktdict = dict(pool_id=newPoolRow.iid,
                                idx=state[0],
                                pktlen=pkt.DATA_LEN,
                                type=head.comptype,
                                framecnt=pkt.FRAME_CNT,
                                seqcnt=pkt.SEQ_CNT,
                                raw=tm_raw)

            else:
                return

            state[0] += 1
            if state[0] % bulk_insert_size == 0:
                GLib.idle_add(loadinfo.log.set_text, "Loaded {:d} rows.".format(state[0], ))
            return pcktdict

        def mkdict_pus(tmd, tm_raw, truncate=True):
            tm = tmd[0]

            pcktdict = dict(pool_id=newPoolRow.iid,
                            idx=state[0],
                            is_tm=tm.PKT_TYPE,
                            apid=tm.APID,
                            seq=tm.PKT_SEQ_CNT,
                            len_7=tm.PKT_LEN,
                            stc=tm.SERV_TYPE,
                            sst=tm.SERV_SUB_TYPE,
                            destID=tm.DEST_ID if tm.PKT_TYPE == 0 else tm.SOURCE_ID,
                            timestamp=cuc_time_str(tm),
                            data=tmd[1][:MAX_PKT_LEN],
                            raw=tm_raw[:MAX_PKT_LEN])

            state[0] += 1
            if state[0] % bulk_insert_size == 0:
                GLib.idle_add(loadinfo.log.set_text, "Loaded {:d} rows.".format(state[0], ))
            return pcktdict

        if protocol == 'PUS':
            mkdict = mkdict_pus
        elif protocol == 'SPW':
            mkdict = mkdict_spw
        else:
            new_session.rollback()
            new_session.close()
            logger.info("Protocol '{}' not supported".format(protocol))
            loadinfo.log.set_text("Protocol '{}' not supported".format(protocol))
            loadinfo.spinner.stop()
            loadinfo.ok_button.set_sensitive(True)
            return

        loadinfo.log.set_text("Parsing file...")
        DbTools.db_bulk_insert(pool_info.filename, mkdict, bulk_insert_size=bulk_insert_size, brute=brute,
                               protocol=protocol, pecmode=pecmode)

        # self.pool.decode_tmdump_and_process_packets(pool_info.filename, process_tm, brute=brute)
        new_session.commit()
        logger.info("Loaded %d rows." % (state[0] - 1))
        loadinfo.log.set_text("Loaded %d rows." % (state[0] - 1))
        loadinfo.spinner.stop()
        loadinfo.ok_button.set_sensitive(True)
        # Ignore Reply is allowed here, since the instance is passed along
        # pv.Functions('_set_list_and_display_Glib_idle_add', self.active_pool_info, int(self.my_bus_name[-1]), ignore_reply=True)
        # GLib.idle_add(self._set_pool_list_and_display)
        new_session.close()
        logger.info('Loaded Pool: ' + str(pool_info.filename))

    @staticmethod
    def db_bulk_insert(filename, processor, bulk_insert_size=1000, brute=False, checkcrc=True, protocol='PUS', pecmode='warn'):

        with open(filename, 'rb') as buf:

            pcktcount = 0

            new_session = scoped_session_storage()
            new_session.execute('set unique_checks=0,foreign_key_checks=0')

            if protocol == 'PUS':
                buf = buf.read()
                if brute:
                    pckts = extract_pus_brute_search(buf, filename=filename)
                    checkcrc = False  # CRC already performed during brute_search

                else:
                    pckts = extract_pus(buf)

                pcktdicts = []
                for pckt in pckts:
                    if checkcrc:
                        if crc_check(pckt):
                            if pecmode == 'warn':
                                if len(pckt) > 7:
                                    logger.info('db_bulk_insert: [CRC error]: packet with seq nr ' + str(
                                        int(pckt[5:7].hex(), 16)) + '\n')
                                else:
                                    logger.info('INVALID packet -- too short' + '\n')
                            elif pecmode == 'discard':
                                if len(pckt) > 7:
                                    logger.info(
                                        '[CRC error]: packet with seq nr ' + str(
                                            int(pckt[5:7].hex(), 16)) + ' (discarded)\n')
                                else:
                                    logger.info('INVALID packet -- too short' + '\n')
                                continue

                    pcktdicts.append(processor(unpack_pus(pckt), pckt))
                    pcktcount += 1
                    if pcktcount % bulk_insert_size == 0:
                        try:
                            new_session.execute(DbTelemetry.__table__.insert(), pcktdicts)
                            # new_session.bulk_insert_mappings(DbTelemetry, pcktdicts)
                            pcktdicts = []
                        except Exception as err:
                            new_session.rollback()
                            new_session.close()
                            logger.error(err)
                            raise err

                new_session.execute(DbTelemetry.__table__.insert(), pcktdicts)

            elif protocol == 'SPW':
                headers, pckts, remainder = extract_spw(buf)

                pcktdicts_rmap = []
                pcktdicts_feedata = []

                for head, pckt in zip(headers, pckts):

                    if SPW_PROTOCOL_IDS_R[head.bits.PROTOCOL_ID] == 'RMAP':
                        pcktdicts_rmap.append(processor(head, pckt))
                    elif SPW_PROTOCOL_IDS_R[head.bits.PROTOCOL_ID] == 'FEEDATA':
                        pcktdicts_feedata.append(processor(head, pckt))

                    pcktcount += 1
                    if pcktcount % bulk_insert_size == 0:
                        if len(pcktdicts_rmap) > 0:
                            new_session.execute(RMapTelemetry.__table__.insert(), pcktdicts_rmap)
                            pcktdicts_rmap = []
                        if len(pcktdicts_feedata) > 0:
                            new_session.execute(FEEDataTelemetry.__table__.insert(), pcktdicts_feedata)
                            pcktdicts_feedata = []

                if len(pcktdicts_rmap) > 0:
                    new_session.execute(RMapTelemetry.__table__.insert(), pcktdicts_rmap)
                if len(pcktdicts_feedata) > 0:
                    new_session.execute(FEEDataTelemetry.__table__.insert(), pcktdicts_feedata)

            new_session.execute('set unique_checks=1, foreign_key_checks=1')
            new_session.commit()
            new_session.close()


class Verification:
    """
    Packet verification tools
    """

    PKTIDLEN = 4

    @classmethod
    def await_tc_ack(cls, pool_name, pktid=None, idx_from=None, time_from=None, acktypes=(1, 7), timeout=3.):

        t1 = time.time()

        acks_remain = list(acktypes)

        if pktid is None:
            pkt = get_last_tc(pool_name)
            pktid = pkt.raw[:cls.PKTIDLEN]

            if idx_from is None:
                idx_from = pkt.idx

        elif isinstance(pktid, (tuple, list)):
            pktid = cls.mk_pktid(*pktid)

        elif isinstance(pktid, DbTelemetry):
            pktid = pktid.raw[:cls.PKTIDLEN]

            if idx_from is None:
                idx_from = pktid.idx

        else:
            if len(pktid) != cls.PKTIDLEN or not isinstance(pktid, (bytes, bytearray)):
                raise ValueError

        while time.time() - t1 < timeout:

            acks = cls.get_acks(pool_name, idx_from=idx_from, time_from=time_from)
            # filter by pktid
            acks_found = filter_by_discr(acks, TM_HEADER_LEN, cls.PKTIDLEN, pktid)

            for ack in acks_found:
                if ack.sst in acks_remain:
                    acks_remain.remove(ack.sst)

            if len(acks_remain) == 0:
                return True, acks_found.all()

            time.sleep(.1)

        return False, acks_found.all()

    @staticmethod
    def get_acks(pool_name, idx_from=None, time_from=None):

        rows = get_pool_rows(pool_name)
        acks = filter_rows(rows, st=1, idx_from=idx_from, time_from=time_from)

        return acks

    @classmethod
    def mk_pktid(cls, apid, sc):
        pktid = TCHeader()
        pktid.bits.SEC_HEAD_FLAG = 1
        pktid.bits.APID = apid
        pktid.bits.SEQ_FLAGS = 3
        pktid.bits.PKT_SEQ_CNT = sc

        return pktid.raw[:cls.PKTIDLEN]


class LoadInfo(Gtk.Window):
    def __init__(self, parent=None, title="DB Loader"):
        Gtk.Window.__init__(self, transient_for=parent, destroy_with_parent=True)

        self.set_title(title)

        grid = Gtk.VBox()
        logo = Gtk.Image.new_from_file(os.path.join(cfg.get('paths', 'ccs'), 'pixmap/ccs_logo_2.svg'))

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        # self.spinner.start()
        self.log = Gtk.Label()
        self.ok_button = Gtk.Button.new_with_label('OK')
        self.ok_button.connect('clicked', self.destroy_window)

        grid.pack_start(logo, 1, 1, 0)
        grid.pack_start(self.spinner, 1, 1, 0)
        grid.pack_start(self.log, 1, 1, 0)
        grid.pack_start(self.ok_button, 1, 1, 0)
        grid.set_spacing(2)

        self.add(grid)

        self.show_all()

    def destroy_window(self, widget, *args):
        try:
            self.destroy()
        except Exception as err:
            print(err)


class TestReport:
    """
    Provides functions for interactive test reporting
    """
    def __init__(self, filename, version, idb_version, gui=False, delimiter='|'):
        super(TestReport, self).__init__()
        self.specfile = filename
        self.delimiter = delimiter
        self.gui = gui
        self.report = dict()

        self.version = int(version)
        self.idb_version = str(idb_version)

        self.step_rowid = dict()
        self._read_test_spec(filename)

        self.testname = self.report[1][0]

    def _read_test_spec(self, filename):
        with open(filename, 'r') as fd:
            csv = fd.readlines()

        for i, line in enumerate(csv):
            items = line.strip().split(self.delimiter)
            self.report[i] = items
            if items[0].startswith('Step '):
                self.step_rowid[items[0]] = i

    def execute_step(self, step, ask=True):
        """

        :param step:
        :param ask:
        :return:
        """
        if not ask:
            return

        try:
            exe_msg = '{}:\n{}'.format(step.upper(), self.report[self.step_rowid[str(step)]][1])
            if self.gui:
                dialog = TestExecGUI(self.report[1][0], exe_msg)
                response = dialog.run()

                if response == Gtk.ResponseType.YES:
                    dialog.destroy()
                    execute = True
                else:
                    dialog.destroy()
                    execute = False

            else:
                execute = input(exe_msg + ':\n(y/n)? > ')
                while execute.lower() not in ('y', 'yes', 'n', 'no'):
                    execute = input(exe_msg + ':\n(y/n)? > ')

                if execute in ('y', 'yes'):
                    execute = True
                else:
                    execute = False

            if execute:
                return
            else:
                pass  # TODO: abort step execution

        except KeyError:
            logger.error('"{}": no such step defined!'.format(str(step)))
            return

    def verify_step(self, step):
        """

        :param step:
        :return:
        """
        try:
            ver_msg = '{}:\n{}'.format(step.upper(), self.report[self.step_rowid[str(step)]][2])
            if self.gui:
                dialog = TestReportGUI(self.report[1][0], ver_msg)
                response = dialog.run()

                if response == Gtk.ResponseType.YES:
                    result = 'VERIFIED'
                    comment = dialog.comment.get_text()
                    dialog.destroy()
                elif response == Gtk.ResponseType.NO:
                    result = 'FAILED'
                    comment = dialog.comment.get_text()
                    dialog.destroy()
                else:
                    dialog.destroy()
                    return

                if comment:
                    result += ' ({})'.format(comment)

            else:
                result = input(ver_msg + ':\n>')

        except KeyError:
            logger.error('"{}": no such step defined!'.format(str(step)))
            return

        self.report[self.step_rowid[str(step)]][3] = result

    def export(self, reportdir=None, reportfile=None):
        """

        :param reportdir:
        :param reportfile:
        """
        if reportfile is None:
            if reportdir is None:
                reportfile = self.specfile.replace('.csv_PIPE', '-TR-{:03d}.csv_PIPE'.format(self.version)).replace('/testspec/', '/testrep/')
            else:
                reportdir += '/' if not reportdir.endswith('/') else ''
                reportfile = reportdir + self.specfile.split('/')[-1].replace('.csv_PIPE', '-TR-{:03d}.csv_PIPE'.format(self.version))

        self.report[1][3] += ' TR-{:03d}, MIB v{}'.format(self.version, self.idb_version)
        self.report[2][3] = time.strftime('%Y-%m-%d')

        buf = '\n'.join([self.delimiter.join(self.report[line]) for line in range(len(self.report))])

        Path(os.path.dirname(reportfile)).mkdir(parents=True, exist_ok=True)  # create directory if it does not exist

        with open(reportfile, 'w') as fd:
            fd.write(buf + '\n')
        logger.info('Report written to {}.'.format(reportfile))
        print('Report written to {}.'.format(reportfile))


class TestReportGUI(Gtk.MessageDialog):
    """
    GUI for the TestReport class
    """
    def __init__(self, testlabel, message):
        super(TestReportGUI, self).__init__(title=testlabel,
                                            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                     Gtk.STOCK_NO, Gtk.ResponseType.NO,
                                                     Gtk.STOCK_YES, Gtk.ResponseType.YES,))

        head, body = self.get_message_area().get_children()
        head.set_text(message)

        cancel, fail, verify = self.get_action_area().get_children()

        cancel.get_child().get_child().get_children()[1].set_label('Skip')
        fail.get_child().get_child().get_children()[1].set_label('FAILED')
        verify.get_child().get_child().get_children()[1].set_label('VERIFIED')

        self.comment = Gtk.Entry()
        self.comment.set_placeholder_text('Optional comment')
        self.get_message_area().add(self.comment)

        verify.grab_focus()

        self.show_all()


class TestExecGUI(Gtk.MessageDialog):
    """
    Dialog window to confirm test step execution
    """
    def __init__(self, testlabel, message):
        super(TestExecGUI, self).__init__(title=testlabel,
                                          buttons=(# Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                   Gtk.STOCK_YES, Gtk.ResponseType.YES,))

        head, body = self.get_message_area().get_children()
        head.set_text(message)

        # abort, exe = self.get_action_area().get_children()
        exe, = self.get_action_area().get_children()

        # abort.get_child().get_child().get_children()[1].set_label('ABORT')
        exe.get_child().get_child().get_children()[1].set_label('EXECUTE')

        exe.grab_focus()

        self.show_all()


class TmParameterDecoderDialog(Gtk.Dialog):
    """
    Interface to define custom paramters
    """
    def __init__(self, parent=None):
        Gtk.Dialog.__init__(self, "Add User Parameter", parent, 0,
                            buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        self.set_border_width(5)

        box = self.get_content_area()
        ok_button = self.get_action_area().get_children()[0]
        ok_button.set_sensitive(False)

        bytebox = Gtk.HBox()

        self.format = Gtk.ComboBoxText()
        self.format.set_model(create_format_model())
        self.format.set_tooltip_text('Format type')
        self.format.connect('changed', self.bitlen_active)
        self.format.connect('changed', self.check_ok_sensitive, ok_button)
        # self.offbi = Gtk.Entry()
        # self.offbi.set_placeholder_text('Bit offset')
        # self.offbi.set_tooltip_text('Bit offset from byte alignment')
        # self.offbi.set_sensitive(False)
        self.bitlen = Gtk.Entry()
        self.bitlen.set_placeholder_text('Length')
        self.bitlen.set_tooltip_text('Length in bits (for uint*) or bytes (ascii*, oct*)')
        self.bitlen.set_sensitive(False)

        bytebox.pack_start(self.format, 0, 0, 0)
        # bytebox.pack_start(self.offbi, 0, 0, 0)
        bytebox.pack_start(self.bitlen, 0, 0, 0)
        bytebox.set_spacing(5)

        self.label = Gtk.Entry()
        self.label.set_placeholder_text('Parameter Label')
        self.label.connect('changed', self.check_ok_sensitive, ok_button)

        box.pack_start(self.label, 0, 0, 0)
        box.pack_end(bytebox, 0, 0, 0)
        box.set_spacing(10)

        self.show_all()

    def check_ok_sensitive(self, unused_widget, button):
        """

        :param unused_widget:
        :param button:
        """
        if len(self.label.get_text()) == 0 or not self.format.get_active_text():
            button.set_sensitive(False)
        else:
            button.set_sensitive(True)

    def bitlen_active(self, widget):
        """

        :param widget:
        """
        if widget.get_active_text().endswith('*'):
            self.bitlen.set_sensitive(True)
            # if widget.get_active_text().startswith(('ascii', 'oct')):
            #     self.offbi.set_sensitive(False)
            # else:
            #     self.offbi.set_sensitive(True)
        else:
            self.bitlen.set_sensitive(False)


class TmDecoderDialog(Gtk.Dialog):
    """
    Interface to define custom packet structures
    """
    def __init__(self, logger, parameter_set=None, parent=None):
        Gtk.Dialog.__init__(self, "Build User Defined Packet Structure", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        # self.set_default_size(780,560)
        self.set_border_width(5)
        self.set_resizable(True)

        self.logger = logger
        self.cfg = cfg

        self.session_factory_idb = scoped_session_idb
        self.session_factory_storage = scoped_session_storage

        box = self.get_content_area()

        slots = self.create_view(parameter_set=parameter_set)
        box.pack_start(slots, 1, 1, 0)

        self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        self.ok_button.set_sensitive(False)

        self.show_all()

    def create_view(self, parameter_set=None):
        """

        :param parameter_set:
        :return:
        """
        parameter_view = self.create_param_view()
        packet = None

        slotbox = Gtk.HBox()
        slotbox.set_homogeneous(True)
        slotbox.set_spacing(50)

        entrybox = Gtk.HBox()

        self.apid = Gtk.Entry()
        self.st = Gtk.Entry()
        self.sst = Gtk.Entry()
        self.label = Gtk.Entry()

        self.apid.set_placeholder_text('APID')
        self.st.set_placeholder_text('Service Type')
        self.sst.set_placeholder_text('Service Subtype')
        self.label.set_placeholder_text('Label')
        self.label.set_tooltip_text('Label for the current configuration')

        self.sid = Gtk.Entry()
        self.sid.set_placeholder_text('SID')
        self.sid.set_tooltip_text('Discriminant, only applicable if ST and SST have a SID defined in the MIB.')

        self.apid.connect('changed', self.check_entry)
        self.st.connect('changed', self.check_entry)
        self.sst.connect('changed', self.check_entry)
        self.label.connect('changed', self.check_entry)

        entrybox.pack_start(self.label, 0, 0, 0)
        entrybox.pack_start(self.apid, 0, 0, 0)
        entrybox.pack_start(self.st, 0, 0, 0)
        entrybox.pack_start(self.sst, 0, 0, 0)
        entrybox.pack_start(self.sid, 0, 0, 0)

        entrybox.set_homogeneous(True)
        entrybox.set_spacing(5)

        # decisionbox = Gtk.HBox()
        #
        # self.given_poition = Gtk.RadioButton.new_with_label_from_widget(None, 'Local')
        # self.given_poition.set_tooltip_text('Decode in given order')
        # self.idb_position = Gtk.RadioButton.new_with_label_from_widget(self.given_poition, 'IDB')
        # self.idb_position.set_tooltip_text('Decode by parameter position given in IDB')
        #
        # decisionbox.pack_start(self.given_poition, 0, 0, 0)
        # decisionbox.pack_start(self.idb_position, 0, 0, 0)

        if parameter_set is not None:

            if self.cfg.has_option('ccs-user_defined_packets', parameter_set):
                packet = json.loads(self.cfg['ccs-user_defined_packets'][parameter_set])
                value = parameter_set
            else:
                for pack in self.cfg['ccs-user_defined_packets']:
                    pack_val = json.loads(self.cfg['ccs-user_defined_packets'][pack])
                    if pack_val[0] == parameter_set:
                        packet = pack_val
                        value = pack

            if packet:
                value = value.split('-')

                self.st.set_text(value[0])
                self.sst.set_text(value[1])
                self.apid.set_text(value[2])
                self.sid.set_text(value[3])

                param_name = []
                for j in packet[1]:
                    param_name.append(j[1])

                slot = self.create_slot(param_name)
                slotbox.pack_start(slot, 1, 1, 0)
            else:
                slot = self.create_slot()
                slotbox.pack_start(slot, 1, 1, 0)

        else:
            slot = self.create_slot()
            slotbox.pack_start(slot, 1, 1, 0)

        # note = Gtk.Label(label="Note: User-Defined_IDB parameter can only be used if IDB order is chosen, User-Defined_Local only for Local order")

        box = Gtk.VBox()
        box.pack_start(parameter_view, 1, 1, 5)
        # box.pack_start(note, 0,0,0)
        box.pack_start(slotbox, 1, 1, 2)
        # box.pack_start(decisionbox, 1, 1, 2)
        box.pack_start(entrybox, 0, 0, 3)

        return box

    def create_param_view(self):
        """

        :return:
        """
        self.treeview = Gtk.TreeView(self.create_parameter_model())

        self.treeview.append_column(Gtk.TreeViewColumn("Parameters", Gtk.CellRendererText(), text=0))
        hidden_column = Gtk.TreeViewColumn("PCF_NAME", Gtk.CellRendererText(), text=1)
        hidden_column.set_visible(False)
        self.treeview.append_column(hidden_column)

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(200, 200)
        # workaround for allocation warning GTK bug
        # grid = Gtk.Grid()
        # grid.attach(self.treeview, 0, 0, 1, 1)
        # sw.add(grid)
        sw.add(self.treeview)

        return sw

    def create_slot(self, group=None):
        """

        :param group:
        :return:
        """
        self.parameter_list = Gtk.ListStore(str, str)
        treeview = Gtk.TreeView(self.parameter_list)
        treeview.set_reorderable(True)

        treeview.append_column(Gtk.TreeViewColumn("Parameters", Gtk.CellRendererText(), text=0))
        hidden_column = Gtk.TreeViewColumn("PCF_NAME", Gtk.CellRendererText(), text=1)
        hidden_column.set_visible(False)
        treeview.append_column(hidden_column)
        treeview.set_headers_visible(False)

        # add parameters if modifying existing configuration
        if group is not None:
            for item in group:
                descr, name = self.name_to_descr(item)
                if descr is not None:
                    self.parameter_list.append([descr, name])

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(100, 200)
        sw.add(treeview)

        bbox = Gtk.HBox()
        bbox.set_homogeneous(True)
        add_button = Gtk.Button(label='Add')
        add_button.connect('clicked', self.add_parameter, self.parameter_list)
        rm_button = Gtk.Button(label='Remove')
        rm_button.connect('clicked', self.remove_parameter, treeview)

        bbox.pack_start(add_button, 1, 1, 0)
        bbox.pack_start(rm_button, 1, 1, 0)

        vbox = Gtk.VBox()
        vbox.pack_start(bbox, 0, 0, 3)
        vbox.pack_start(sw, 1, 1, 0)

        return vbox

    def name_to_descr(self, name):
        """

        :param name:
        :return:
        """
        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pcf_descr, pcf_name FROM pcf WHERE pcf_name="{}"'.format(name))
        name = dbres.fetchall()
        dbcon.close()
        if len(name) != 0:
            return name[0]
        else:
            return None, None

    # def create_parameter_model_old(self):
    #     parameter_model = Gtk.TreeStore(str, str)
    #
    #     dbcon = self.session_factory_idb
    #     #dbres = dbcon.execute('SELECT pid_descr,pid_spid from pid where pid_type=3 and pid_stype=25')
    #     dbres = dbcon.execute('SELECT pid_descr,pid_spid from pid order by pid_type,pid_pi1_val')
    #     hks = dbres.fetchall()
    #     for hk in hks:
    #         it = parameter_model.append(None, [hk[0], None])
    #         dbres = dbcon.execute('SELECT pcf.pcf_descr, pcf.pcf_name from pcf left join plf on\
    #          pcf.pcf_name=plf.plf_name left join pid on plf.plf_spid=pid.pid_spid where pid.pid_spid={}'.format(hk[1]))
    #         params = dbres.fetchall()
    #         [parameter_model.append(it, [par[0], par[1]]) for par in params]
    #     dbcon.close()
    #     self.useriter_IDB = parameter_model.append(None, ['User-defined_IDB', None])
    #     self.useriter_local = parameter_model.append(None, ['User-defined_local', None])
    #     for userpar in self.cfg['ccs-user_decoders']:
    #         parameter_model.append(self.useriter_IDB, [userpar, None])
    #     for userpar in self.cfg['ccs-decode_parameters']:
    #         parameter_model.append(self.useriter_local, [userpar, None])
    #
    #     return parameter_model

    def create_parameter_model(self):
        """

        :return:
        """
        parameter_model = Gtk.TreeStore(str, str)
        self.store = parameter_model

        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pid_descr,pid_spid,pid_type from pid order by pid_type,pid_stype,pid_pi1_val')
        hks = dbres.fetchall()

        topleveliters = {}
        for hk in hks:

            if not hk[2] in topleveliters:
                serv = parameter_model.append(None, ['Service ' + str(hk[2]), None])
                topleveliters[hk[2]] = serv

            it = parameter_model.append(topleveliters[hk[2]], [hk[0], None])

            dbres = dbcon.execute('SELECT pcf.pcf_descr, pcf.pcf_name from pcf left join plf on pcf.pcf_name=plf.plf_name left join pid on \
                                   plf.plf_spid=pid.pid_spid where pid.pid_spid={} ORDER BY pcf.pcf_descr'.format(hk[1]))
            params = dbres.fetchall()
            for par in params:
                parameter_model.append(it, [*par])

        dbcon.close()

        # # add user defined PACKETS
        # self.user_tm_decoders = user_tm_decoders_func()
        # topit = parameter_model.append(None, ['UDEF'])
        # for hk in self.user_tm_decoders:
        #     it = parameter_model.append(topit, ['UDEF|{}'.format(self.user_tm_decoders[hk][0])])
        #     for par in self.user_tm_decoders[hk][1]:
        #         parameter_model.append(it, [par[1]])

        # add data pool items
        self.useriter = parameter_model.append(None, ['Data pool', None])
        for dp in _dp_items:
            dp_item = '{} ({})'.format(_dp_items[dp]['descr'], dp)
            parameter_model.append(self.useriter, [dp_item, 'dp_item'])

        # add user defined PARAMETERS with positional info
        self.useriter = parameter_model.append(None, ['User defined', None])
        for userpar in self.cfg[CFG_SECT_PLOT_PARAMETERS]:
            parameter_model.append(self.useriter, [userpar, 'user_defined'])

        # add user defined PARAMETERS without positional info
        for userpar in self.cfg[CFG_SECT_DECODE_PARAMETERS]:
            parameter_model.append(self.useriter, [userpar, 'user_defined_nopos'])

        return parameter_model

    def add_parameter(self, widget, listmodel):
        """

        :param widget:
        :param listmodel:
        :return:
        """
        par_model, par_iter = self.treeview.get_selection().get_selected()
        if par_model[par_iter][1] is None:
            return

        # hk = par_model[par_iter].parent[0]

        if par_model[par_iter].parent is None:
            return

        # elif hk not in ['User-defined_IDB', 'User-defined_local']:
        #     param = par_model[par_iter]
        #     listmodel.append([*param])

        else:
            param = par_model[par_iter]
            listmodel.append([*param])

        return

    def remove_parameter(self, widget, listview):
        """

        :param widget:
        :param listview:
        :return:
        """
        model, modeliter = listview.get_selection().get_selected()

        if modeliter is None:
            return

        model.remove(modeliter)
        return

    def check_entry(self, widget):
        """

        :param widget:
        """
        if self.apid.get_text_length() and self.st.get_text_length() and self.sst.get_text_length \
                and self.label.get_text_length():
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)


class UserParameterDialog(Gtk.MessageDialog):
    """
    Interface to edit a user-defined parameter
    """
    def __init__(self, parent=None, edit=None):
        Gtk.Dialog.__init__(self, "Edit User Parameter", parent, 0,
                            buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        self.cfg = cfg
        self.set_border_width(5)

        box = self.get_content_area()
        ok_button = self.get_action_area().get_children()[0]
        ok_button.set_sensitive(False)

        hbox = Gtk.HBox()

        self.apid = Gtk.Entry()
        self.st = Gtk.Entry()
        self.sst = Gtk.Entry()
        self.apid.set_placeholder_text('APID')
        self.apid.connect('changed', self.check_entry, ok_button)
        self.st.set_placeholder_text('Service Type')
        self.st.connect('changed', self.check_entry, ok_button)
        self.sst.set_placeholder_text('Service Subtype')
        self.sst.connect('changed', self.check_entry, ok_button)
        self.sid = Gtk.Entry()
        self.sid.set_placeholder_text('SID')
        self.sid.set_tooltip_text('Discriminant (i.e. PI1VAL)')

        hbox.pack_start(self.apid, 0, 0, 0)
        hbox.pack_start(self.st, 0, 0, 0)
        hbox.pack_start(self.sst, 0, 0, 0)
        hbox.pack_start(self.sid, 0, 0, 0)
        hbox.set_homogeneous(True)
        hbox.set_spacing(5)

        bytebox = Gtk.HBox()

        self.bytepos = Gtk.Entry()
        self.bytepos.set_placeholder_text('Byte Offset')
        self.bytepos.set_tooltip_text('Including {} ({} for TCs) header bytes, e.g. byte 0 in TM source data -> offset={}'
                                      .format(TM_HEADER_LEN, TC_HEADER_LEN, TM_HEADER_LEN))
        self.bytepos.connect('changed', self.check_entry, ok_button)
        self.format = Gtk.ComboBoxText()
        self.format.set_model(create_format_model())
        self.format.set_tooltip_text('Format type')
        self.format.connect('changed', self.bitlen_active)
        self.offbi = Gtk.Entry()
        self.offbi.set_placeholder_text('Bit Offset')
        self.offbi.set_tooltip_text('Bit Offset (optional)')
        self.offbi.set_sensitive(False)
        self.bitlen = Gtk.Entry()
        self.bitlen.set_placeholder_text('Length')
        self.bitlen.set_tooltip_text('Length in bits (for uint*) and bytes (ascii*, oct*)')
        self.bitlen.set_sensitive(False)

        bytebox.pack_start(self.bytepos, 0, 0, 0)
        bytebox.pack_start(self.format, 0, 0, 0)
        bytebox.pack_start(self.offbi, 0, 0, 0)
        bytebox.pack_start(self.bitlen, 0, 0, 0)
        bytebox.set_spacing(5)

        self.label = Gtk.Entry()
        self.label.set_placeholder_text('Parameter Label')
        self.label.connect('changed', self.check_entry, ok_button)

        box.pack_start(self.label, 0, 0, 0)
        box.pack_end(bytebox, 0, 0, 0)
        box.pack_end(hbox, 0, 0, 0)
        box.set_spacing(10)

        if edit is not None:
            pars = json.loads(self.cfg[CFG_SECT_PLOT_PARAMETERS][edit])
            self.label.set_text(edit)
            if 'ST' in pars:
                self.st.set_text(str(pars['ST']))
            if 'SST' in pars:
                self.sst.set_text(str(pars['SST']))
            if 'APID' in pars:
                self.apid.set_text(str(pars['APID']))
            if 'SID' in pars and pars['SID'] is not None:
                self.sid.set_text(str(pars['SID']))
            if 'bytepos' in pars:
                self.bytepos.set_text(str(pars['bytepos']))
            if 'format' in pars:
                fmt_dict = {a: b for b, a in fmtlist.items()}
                fmt = pars['format']
                for fk in ('uint', 'ascii', 'oct'):
                    if fmt.startswith(fk):
                        self.bitlen.set_text(fmt.replace(fk, ''))
                        fmt = fk
                        break
                model = self.format.get_model()
                it = [row.iter for row in model if row[0] == fmt_dict[fmt]][0]
                self.format.set_active_iter(it)
            if 'offbi' in pars:
                self.offbi.set_text(str(pars['offbi']))

        self.show_all()

    def check_entry(self, widget, ok_button):
        """

        :param widget:
        :param ok_button:
        """
        if self.apid.get_text_length() and self.st.get_text_length() and self.sst.get_text_length \
                and self.label.get_text_length() and self.bytepos.get_text_length():
            ok_button.set_sensitive(True)
        else:
            ok_button.set_sensitive(False)

    def bitlen_active(self, widget):
        """

        :param widget:
        """
        if widget.get_active_text() == 'uint*':
            self.bitlen.set_sensitive(True)
            self.offbi.set_sensitive(True)
        elif widget.get_active_text() in ('ascii*', 'oct*'):
            self.bitlen.set_sensitive(True)
            self.offbi.set_sensitive(False)
        else:
            self.bitlen.set_sensitive(False)
            self.offbi.set_sensitive(False)


# class RemoveUserParameterDialog(Gtk.Dialog):
#     def __init__(self, cfg, parent=None):
#         Gtk.Dialog.__init__(self, "Remove User Defined Parameter", parent, 0)
#         self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
#
#         self.cfg = cfg
#
#         box = self.get_content_area()
#
#         self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
#         self.ok_button.set_sensitive(False)
#
#         self.remove_name = Gtk.ComboBoxText.new_with_entry()
#         self.remove_name.set_tooltip_text('Parameter')
#         self.remove_name_entry = self.remove_name.get_child()
#         self.remove_name_entry.set_placeholder_text('Label')
#         self.remove_name_entry.set_width_chars(5)
#         self.remove_name.connect('changed', self.fill_remove_mask)
#
#         self.remove_name.set_model(self.create_remove_model())
#
#         box.pack_start(self.remove_name, 0, 0, 0)
#
#         self.show_all()
#
#     def create_remove_model(self):
#         model = Gtk.ListStore(str)
#
#         for decoder in self.cfg[CFG_SECT_PLOT_PARAMETERS].keys():
#             model.append([decoder])
#         return model
#
#     def fill_remove_mask(self, widget):
#         decoder = widget.get_active_text()
#
#         if self.cfg.has_option(CFG_SECT_PLOT_PARAMETERS, decoder):
#             self.ok_button.set_sensitive(True)
#         else:
#             self.ok_button.set_sensitive(False)


# class EditUserParameterDialog(Gtk.Dialog):
#     def __init__(self, cfg, parent=None):
#         Gtk.Dialog.__init__(self, "Edit User Defined Parameter", parent, 0)
#         self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
#
#         self.cfg = cfg
#
#         box = self.get_content_area()
#
#         self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
#         self.ok_button.set_sensitive(False)
#
#         self.edit_name = Gtk.ComboBoxText.new_with_entry()
#         self.edit_name.set_tooltip_text('Parameter')
#         self.edit_name_entry = self.edit_name.get_child()
#         self.edit_name_entry.set_placeholder_text('Label')
#         self.edit_name_entry.set_width_chars(5)
#         self.edit_name.connect('changed', self.fill_edit_mask)
#
#         self.edit_name.set_model(self.create_edit_model())
#
#         box.pack_start(self.edit_name, 0, 0, 0)
#
#         self.show_all()
#
#     def create_edit_model(self):
#         model = Gtk.ListStore(str)
#
#         for decoder in self.cfg[CFG_SECT_PLOT_PARAMETERS].keys():
#             model.append([decoder])
#         return model
#
#     def fill_edit_mask(self, widget):
#         decoder = widget.get_active_text()
#
#         if self.cfg.has_option(CFG_SECT_PLOT_PARAMETERS, decoder):
#             self.ok_button.set_sensitive(True)
#         else:
#             self.ok_button.set_sensitive(False)


class ChangeCommunicationDialog(Gtk.Dialog):
    """
    This dialog is used to manage the main_communication in the CCS via a GUI
    """
    def __init__(self, cfg, main_instance, parent=None):
        """

        :param cfg: Is the config file
        :param main_instance: Is the project name
        :param parent: Given Gtk.Window instance
        """
        Gtk.Dialog.__init__(self, "Communication", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        self.box = self.get_content_area()  # Dialogs are not running without this

        self.label = Gtk.Label('"Main Communication" \n is to these Applications')

        self.cfg = cfg
        self.parent = parent

        # Set up a variable which will hold the end results
        self.new_communication = communication

        # Filter all connection of the CCS out of all dbus connections
        self.our_con = []
        for service in dbus.SessionBus().list_names():
            if service[:-1] in self.cfg['ccs-dbus_names'].values():
                self.our_con.append(service)

        self.change_box = self.setup_change_box()

        self.tick_box = self.get_tick_box()

        self.box.pack_start(self.label, 0, 0, 4)
        self.box.pack_start(self.change_box, 0, 0, 4)
        self.box.pack_start(self.tick_box, 0, 0, 4)
        self.show_all()

    def setup_change_box(self):
        """
        Sets up the main Box in which the change happens

        :return: a Gtk.Box
        """
        main_box = Gtk.HBox()

        label_box = Gtk.VBox()  # Used only for the names
        change_box = Gtk.VBox() # used only for the changing

        for name in communication:
            # Label_Box
            lab = Gtk.Label(name.capitalize() + str('        ')) # The long space is made that GUI looks better
            label_box.pack_start(lab, 0, 0, 8)

            #Change_Box
            entry_list, nbr = self.get_entry_list(name)

            #Start each Changing box here
            communication_entry = Gtk.ComboBox.new_with_model(entry_list)
            communication_entry.set_title(name) #Give the boxes names to separate them
            communication_entry.connect('changed', self.main_com_changed)

            # Necessary for Combobox but not importent for program
            renderer_text = Gtk.CellRendererText()
            communication_entry.pack_start(renderer_text, True)
            communication_entry.add_attribute(renderer_text, "text", 0)

            communication_entry.set_active(nbr)
            change_box.pack_start(communication_entry, 0, 0, 0)


        main_box.pack_start(label_box, 0, 0, 0)
        main_box.pack_start(change_box, 0, 0, 0)

        return main_box

    def get_entry_list(self, app):
        """
        Returns a List of all active instance of the given application in this main_instance (project)

        :param app: application name (poolviewer,...)
        :return: liststore and listplace
        """
        count = 0   # Counts the amount of entries
        ret = 0     # Saves the place of the main_communication application
        liststore = Gtk.ListStore(str)
        liststore.append(['-']) # Append an empty entry to each list, so that all Boxes show something
        for service in self.our_con:
            if service[:-1] == cfg['ccs-dbus_names'][app]:  # Filer all instance of given application
                if service == self.parent.my_bus_name:  # If it is the calling application dbus cannot be used, do this
                    liststore.append([service[-1]])
                    count += 1  # The list just got longer
                    if str(communication[app]) == str(service[-1]):     # Check if it is the main_communication
                        ret = count
                    continue
                conn = dbus_connection(app, service[-1])
                if conn.Variables('main_instance') == self.parent.main_instance: # Check if both are in the same instance
                    liststore.append([service[-1]])
                    count += 1  # The list just got longer
                    if str(communication[app]) == str(service[-1]):     # Check if it is the main_communication
                        ret = count

        return liststore, ret

    def main_com_changed(self, widget):
        """
        Is called when some connection is changed

        :param widget:
        :return:
        """
        entry = widget.get_model()[widget.get_active()][0]
        # Put in the selected entry, if connection should be switched of use 0
        try:
            self.new_communication[widget.get_title()] = int(entry)
        except:
            self.new_communication[widget.get_title()] = 0

        return

    def get_tick_box(self):
        """
        Creates the Check Button

        :return: a Gtk.Box
        """
        main_box = Gtk.VBox()
        self.change_button = Gtk.CheckButton.new_with_label('Entire Project')
        self.change_button.set_tooltip_text('Change for the entire {} project (recommended) or only for the {} {}'.format(self.parent.main_instance, self.parent.my_bus_name.split('.')[1].capitalize(), self.parent.my_bus_name[-1]))
        self.change_button.set_active(True)
        #self.change_button.connect('toggled', self.tick_changed)

        main_box.pack_start(self.change_button, 0, 0, 0)

        return main_box


class ProjectDialog(Gtk.Dialog):
    """
    Dialog that optionally pops up at CCS/TST start-up to allow for project and IDB configuration
    """

    def __init__(self):
        super(ProjectDialog, self).__init__()

        self.set_title('Project configuration')
        self.set_default_size(300, 100)

        self.project_selection = self._create_project_selection()
        self.idb_selection = self._create_idb_selection()

        self.cfg = cfg
        ca = self.get_content_area()
        ca.set_spacing(2)

        project_label = Gtk.Label('Project')
        project_label.set_size_request(80, -1)
        project_label.set_xalign(0)
        project_box = Gtk.Box(Gtk.Orientation.HORIZONTAL)
        project_box.pack_start(project_label, 0, 0, 10)
        project_box.pack_start(self.project_selection, 1, 1, 0)
        ca.add(project_box)

        idb_label = Gtk.Label('IDB schema')
        idb_label.set_size_request(80, -1)
        idb_label.set_xalign(0)
        idb_box = Gtk.Box(Gtk.Orientation.HORIZONTAL)
        idb_box.pack_start(idb_label, 0, 0, 10)
        idb_box.pack_start(self.idb_selection, 1, 1, 0)
        ca.add(idb_box)

        self.add_buttons('OK', 1, 'Cancel', 2)

        self.connect('response', self._write_config)
        self.connect('delete-event', Gtk.main_quit)

        self.show_all()

        self.action_area.get_children()[0].grab_focus()  # set focus to OK button

    @staticmethod
    def _create_project_selection():
        project_selection = Gtk.ComboBoxText()

        ccs_path = cfg.get('paths', 'ccs')
        ccs_path += '/' if not ccs_path.endswith('/') else ''
        projects = glob.glob(ccs_path + PCPREFIX + '*')

        projects = [p.replace(ccs_path + PCPREFIX, '').replace('.py', '') for p in projects]

        for p in projects:
            project_selection.append(p, p)

        set_as = cfg.get('ccs-database', 'project')
        project_selection.set_active_id(set_as)

        return project_selection

    @staticmethod
    def _create_idb_selection():
        idb_selection = Gtk.ComboBoxText()

        mibs = scoped_session_idb.execute('show databases').fetchall()
        mibs = [mib for mib, in mibs if mib.count('mib')]

        for m in mibs:
            idb_selection.append(m, m)

        set_as = cfg.get('database', 'mib-schema')
        idb_selection.set_active_id(set_as)

        return idb_selection

    def _write_config(self, widget, data):
        if data == 1:

            self.cfg.save_option_to_file('project', 'name', self.project_selection.get_active_text())
            self.cfg.save_option_to_file('database', 'mib-schema', self.idb_selection.get_active_text())

            self.destroy()
            Gtk.main_quit()

        else:
            self.close()
            sys.exit()


# some default variable definitions that require functions defined above

# create local look-up tables for data pool items from MIB
try:
    DP_ITEMS_SRC_FILE = cfg.get('database', 'datapool-items')
    if DP_ITEMS_SRC_FILE:
        # get DP from file
        _dp_items = get_data_pool_items(src_file=DP_ITEMS_SRC_FILE, as_dict=True)
    else:
        raise ValueError
except (FileNotFoundError, ValueError, confignator.config.configparser.NoOptionError):
    if 'DP_ITEMS_SRC_FILE' not in locals():
        DP_ITEMS_SRC_FILE = None
    logger.warning('Could not load data pool from file: {} Using MIB instead.'.format(DP_ITEMS_SRC_FILE))
    _dp_items = get_data_pool_items(as_dict=True)
finally:
    # DP_IDS_TO_ITEMS = {int(k[0]): k[1] for k in _dp_items}
    DP_IDS_TO_ITEMS = {k: _dp_items[k]['descr'] for k in _dp_items}
    DP_ITEMS_TO_IDS = {_dp_items[k]['descr']: k for k in _dp_items}

# S13 header/offset info
try:
    _s13_info = get_tm_parameter_sizes(13, 1)
    SDU_PAR_LENGTH = _s13_info[0][-1]
    # length of PUS + source header in S13 packets (i.e. data to be removed when collecting S13)
    S13_HEADER_LEN_TOTAL = TM_HEADER_LEN + sum([p[-1] for p in _s13_info])
    S13_DATALEN_PAR_OFFSET, S13_DATALEN_PAR_SIZE = TM_HEADER_LEN + sum([x[1] for x in _s13_info[:-1]]), _s13_info[-1][1]
except (SQLOperationalError, NotImplementedError, IndexError):
    logger.warning('Could not get S13 info from MIB, using default values')
    SDU_PAR_LENGTH = 1
    S13_HEADER_LEN_TOTAL = 21
    S13_DATALEN_PAR_OFFSET = 19
    S13_DATALEN_PAR_SIZE = 2

