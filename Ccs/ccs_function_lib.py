import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk, GLib, Notify, GdkPixbuf
import subprocess
import struct
import crcmod
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
import glob
import numpy as np
import logging.handlers
from database.tm_db import scoped_session_maker, DbTelemetry, DbTelemetryPool, RMapTelemetry, FEEDataTelemetry
from sqlalchemy.sql.expression import func

from s2k_partypes import ptt, ptype_parameters, ptype_values
import confignator
import importlib


cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))

PCPREFIX = 'packet_config_'

project = cfg.get('ccs-database', 'project')
project_cfg = PCPREFIX + str(project)
packet_config = importlib.import_module(project_cfg)


PUS_VERSION, TMHeader, TCHeader, PHeader, TM_HEADER_LEN, TC_HEADER_LEN, P_HEADER_LEN, PEC_LEN, MAX_PKT_LEN, timepack,\
timecal, calc_timestamp, CUC_OFFSET, CUC_EPOCH = \
    [packet_config.PUS_VERSION, packet_config.TMHeader, packet_config.TCHeader, packet_config.PHeader,
     packet_config.TM_HEADER_LEN, packet_config.TC_HEADER_LEN, packet_config.P_HEADER_LEN, packet_config.PEC_LEN,
     packet_config.MAX_PKT_LEN, packet_config.timepack, packet_config.timecal, packet_config.calc_timestamp,
     packet_config.CUC_OFFSET, packet_config.CUC_EPOCH]

PLM_PKT_PREFIX_TC_SEND = packet_config.PLM_PKT_PREFIX_TC_SEND
PLM_PKT_SUFFIX = packet_config.PLM_PKT_SUFFIX

FMT_TYPE_PARAM = packet_config.FMT_TYPE_PARAM

if cfg.has_section('ccs-user_defined_packets'):
    user_tm_decoders = {k: json.loads(cfg['ccs-user_defined_packets'][k]) for k in cfg['ccs-user_defined_packets']}
else:
    user_tm_decoders = {}

uuuu = 0
used_user_defined_parameter = None
crctype = 'crc-ccitt-false'
crc = crcmod.predefined.mkCrcFun(crctype)

# Set up logger
logger = logging.getLogger('CFL')

LOGLEVEL_DICT = {'DEBUG': logging.DEBUG,
                 'INFO': logging.INFO,
                 'WARNING': logging.WARNING,
                 'ERROR': logging.ERROR,
                 'CRITICAL': logging.CRITICAL}

counters = {}

pid_offset = int(cfg.get('ccs-misc', 'pid_offset'))

communication = {name: 0 for name in cfg['ccs-dbus_names']}

scoped_session_idb = scoped_session_maker('idb', idb_version=None)
scoped_session_storage = scoped_session_maker('storage')

fmtlist = {'INT8': 'b', 'UINT8': 'B', 'INT16': 'h', 'UINT16': 'H', 'INT32': 'i', 'UINT32': 'I', 'INT64': 'q',
           'UINT64': 'Q', 'FLOAT': 'f', 'DOUBLE': 'd', 'INT24': 'i24', 'UINT24': 'I24', 'bit*': 'bit'}

personal_fmtlist = ['uint', 'int', 'ascii', 'oct']

fmtlengthlist = {'b': 1, 'B': 1, 'h': 2, 'H': 2, 'i': 4, 'I': 4, 'q': 8,
                 'Q': 8, 'f': 4, 'd': 8, 'i24': 3, 'I24': 3}

# get format and offset of HK SID
SID_FORMAT = {1: '>B', 2: '>H', 4: '>I'}
sidfmt = scoped_session_idb.execute('SELECT PIC_PI1_OFF,PIC_PI1_WID FROM mib_smile_sxi.pic where PIC_TYPE=3 and PIC_STYPE=25').fetchall()
if len(sidfmt) != 0:
    SID_OFFSET, SID_BITSIZE = sidfmt[0]
    SID_SIZE = int(SID_BITSIZE / 8)
else:
    SID_SIZE = 2
    SID_OFFSET = TM_HEADER_LEN
    logger.warning('HK SID definition not found in MIB, using default: OFFSET={}, SIZE={}!'.format(SID_OFFSET, SID_SIZE))

Notify.init('cfl')


def get_scoped_session_idb(idb_version=None):
    return scoped_session_maker('idb', idb_version=idb_version)


def get_scoped_session_storage():
    return scoped_session_maker('storage')


def start_app(console, file_path, wd, *args):
    # gui argument only used for poolmanager since it does not have an automatic gui
    if not os.path.isfile(file_path):
        raise FileNotFoundError('The file could not be found: {}'.format(file_path))

    if console is True:
        command = ''
        command += 'nohup python3 '
        command += file_path
        for arg in args:
            command += ' '
            command += arg
        command += ' >/dev/null 2>&1 &'
        logger.debug('command which will be executed: {}'.format(command))
        os.system(command)
    else:
        subprocess.Popen(['python3', file_path, *args], cwd=wd)

    return

# Start the poolviewer
# Argumnet gives the possibility to run file in the console to see print comands
def start_pv(console=True, *args):
    """
    Gets the path of the Startfile for the Poolviewer and executes it
    :param console: If False will be run in Console, otherwise will be run in seperate Environment
    :return:
    """

    '''
    if argument is False:
        file_path = os.path.join(os.path.dirname(__file__), 'startpv.py')
        pop_pv_pmgr = subprocess.Popen(['python3', file_path])
    else:
        pop_pv_pmgr = os.system('nohup python3 startpv.py </dev/null >/dev/null 2>&1 &')
    return
    '''
    # This check is done because if somebody wants to set a flag like name of group one can only type
    # cfl.start_pv(-smile-)
    if not isinstance(console, bool):
        args += (console,)
        console = True

    directory = confignator.get_option('paths', 'ccs')
    file_path = os.path.join(directory, 'poolview_sql.py')
    start_app(console, file_path, directory, *args)

    return

# Start only PoolManager
def start_pmgr(console=True, *args):
    """
    Gets the path of the Startfile for the Poolmanager and executes it
    :param console: If False will be run in Console, otherwise will be run in seperate Environment
    :return:
    """

    if not isinstance(console, bool):
        args += (console,)
        console = True

    directory = confignator.get_option('paths', 'ccs')
    file_path = os.path.join(directory, 'pus_datapool.py')
    start_app(console, file_path, directory, *args)

    return


# Start Editor
# Argumnet gives the possibility to run file in the console to see print comands
def start_editor(console=True, *args):
    """
    Gets the path of the Startfile for the Editor and executes it
    :param console: If False will be run in Console, otherwise will be run in seperate Environment
    :return:
    """

    if not isinstance(console, bool):
        args += (console,)
        console = True

    directory = confignator.get_option('paths', 'ccs')
    file_path = os.path.join(directory, 'editor.py')

    if '--terminal' in args:
        args = list(args)
        args.remove('--terminal')
        os.system(' '.join(['python3', file_path, *args]))
    else:
        start_app(console, file_path, directory, *args)

    return

# Start Parameter Monitor
# Argumnet gives the possibility to run file in the console to see print comands
def start_monitor(console= True, *args):
    """
    Gets the path of the Startfile for the Monitor and executes it
    :param console: If False will be run in Console, otherwise will be run in seperate Environment
    :return:
    """

    if not isinstance(console, bool):
        args += (console,)
        console = True

    directory = confignator.get_option('paths', 'ccs')
    file_path = os.path.join(directory, 'monitor.py')
    start_app(console, file_path, directory, *args)

    return

# Start Parameter Plotter
# Argumnet gives the possibility to run file in the console to see print comands
def start_plotter(console= True, *args):
    """
    Gets the path of the Startfile for the Plotter and executes it
    :param console: If False will be run in Console, otherwise will be run in seperate Environment
    :return:
    """

    if not isinstance(console, bool):
        args += (console,)
        console = True

    directory = confignator.get_option('paths', 'ccs')
    file_path = os.path.join(directory, 'plotter.py')
    start_app(console, file_path, directory, *args)

    return

def start_tst(console=False, *args):
    directory = confignator.get_option('paths', 'tst')
    file_path = os.path.join(directory, 'tst/main.py')
    start_app(console, file_path, directory, *args)
    return


def start_progress_view(console=False, *args):
    directory = confignator.get_option('paths', 'tst')
    file_path = os.path.join(directory, 'progress_view/progress_view.py')
    start_app(console, file_path, directory, *args)
    return


def start_log_viewer(console=False, *args):
    directory = confignator.get_option('paths', 'tst')
    file_path = os.path.join(directory, 'log_viewer/log_viewer.py')
    start_app(console, file_path, directory, *args)
    return


def start_config_editor(console=False, *args):
    file_path = confignator.get_option('start-module', 'config-editor')
    directory = os.path.dirname(file_path)
    start_app(console, file_path, directory, *args)
    return


# This sets up a logging client for the already running TCP-logging Server,
# The logger is returned with the given name an can be used like a normal logger
def start_logging(name):
    level = cfg.get('ccs-logging', 'level')
    loglevel = LOGLEVEL_DICT[level]

    rootLogger = logging.getLogger('')
    rootLogger.setLevel(loglevel)
    socketHandler = logging.handlers.SocketHandler('localhost', logging.handlers.DEFAULT_TCP_LOGGING_PORT)

    # don't bother with a formatter, since a socket handler sends the event as an unformatted pickle
    rootLogger.addHandler(socketHandler)
    log = logging.getLogger(name)
    return log


# This returns a dbus connection to a given Application-Name
def dbus_connection(name, instance=1):
    if instance == 0:
        logger.warning('There is no main instance of {} given in the project'.format(name))
        return False

    if not instance:
        instance = 1

    dbus_type = dbus.SessionBus()
    try:
        Bus_Name = cfg.get('ccs-dbus_names', name)
    except:
        print(str(name) + ' is not a valid DBUS name')
        print(str(name) + ' could not be found in config file')
        logger.warning(str(name) + ' could not be found in config file')
    Bus_Name += str(instance)

    try:
        dbuscon = dbus_type.get_object(Bus_Name, '/MessageListener')
        return dbuscon
    except:
        print('Connection to ' + str(name) + ' is not possible')
        # print('Please start ' + str(name) + ' if it is not running')
        logger.warning('Connection to ' + str(name) + ' is not possible')
        return False


# Returns True if application is running or False if not
def is_open(name, instance=1):
    dbus_type = dbus.SessionBus()
    try:
        #dbus_connection(name, instance)
        Bus_Name = cfg.get('ccs-dbus_names', name)
        Bus_Name += str(instance)
        dbus_type.get_object(Bus_Name, '/MessageListener')
        return True
    except:
        return False


def show_functions(conn, filter=None):
    """
    Show all available functions for a CCS application
    @param conn: A Dbus connection
    @param filter: A string which filters the results
    @return: A list of available functions
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
    @param dbus_con: A Dbus connection
    @param argument: An argument which can be sent for testing purposes
    @return: If the connection is made
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
    @param dbus_con: A Dbus connection
    @param function_name: The function to call as a string
    @param args: The arguments for the function
    @param kwargs: The keyword arguments for the function as as Dict
    @return:
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
    @param dbus_con: A Dbus connection
    @param variable_name: The variable
    @param args: The value to change the variable to, if nothing is given the value of the Variable is returned
    @return: Either the variable value or None if Variable was changed
    """
    args = (python_to_dbus(value, True) for value in args)

    result = dbus_con.Variables(str(variable_name), 'user_console_is_True', *args)

    result = dbus_to_python(result, True)

    return result

def Dictionaries(dbus_con, dictionary_name, *args):
    """
    The user friendly version to use the Dictionaries method exported by all CCS applications via DBus, lets one change
    and get values or the entire Dictionary for all availabe Dictionaries of a CCS application
    @param dbus_con: A Dbus connection
    @param dictionary_name: The dictionary name
    @param args: A key of the dictionary to get the corresponding value, or a key and a value to change the value for a
    key, if not given the entire dictionary is returned
    @return: The entire dictionary, a value for a given key or None if a value was changed
    """
    args = (python_to_dbus(value, True) for value in args)

    result = dbus_con.Dictionaries(str(dictionary_name), 'user_console_is_True', *args)

    result = dbus_to_python(result, True)

    return result

def dict_to_dbus_kwargs(arguments={}, user_console = False):
    """
    Converts a dictionary to kwargs dbus does understand and if necessary and requested changes NoneType to 'NoneType'
    @param arguments: The to converting dictionary
    @return: The dbus Dictionary which simulates the kwargs
    """
    if user_console:
        for key in arguments.keys():
            if arguments[key] is None:
                arguments[key] = 'NoneType'

    return dbus.Dictionary({'kwargs': dbus.Dictionary(arguments, signature='sv')})


# Converts dbus types to python types
def dbus_to_python(data, user_console=False):
    """
    Convets dbus Types to Python Types
    @param data: Dbus Type variables or containers
    @param user_console: Flag to check for NoneType arguments
    @return: Same data as python variables or containers
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
    @param data: Dbus Type variables or containers
    @param user_console: Flag to check for NoneType arguments
    @return: Same data for python variables, same data for container types as dbus containers
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
    @param func: The function where the decorator should be used
    @return: The wrapped function
    """
    def wrapper(*args, **kwargs):
        return dbus_to_python(func(*args, **kwargs))
    return wrapper


def set_monitor(pool_name=None, param_set=None):
    if is_open('monitor'):
        monitor = dbus_connection('monitor', communication['monitor'])
    else:
        print('The Parmameter Monitor is not running')
        return

    if pool_name is not None:
        monitor.Functions('set_pool', pool_name)
    else:
        print('Pool Name has to be specified (cfl.set_monitor(pool_name, parmeter_set))')
        return

    if param_set is not None:
        # Ignore_reply is ok here
        monitor.Functions('monitor_setup', param_set, ignore_reply=True)
    else:
        monitor.Functions('monitor_setup', ignore_reply=True)

    return


def ptt_reverse(type):

    """
    Returns the ptc location (first layer) of a Type stored in s2k_partypes 'ptt'
    :param type: Has to be a type given in s2k_partypes 'ptt'
    :return: ptc location
    """

    if type.startswith('oct'):
        return [7, type[3:]]
    elif type.startswith('ascii'):
        return [8, type[5:]]

    for i in ptt: # First Section
        for j in ptt[i]: # Second Section
            if ptt[i][j] == type: # Check for type
                return [i, j]

    return False


'''
def ptt_reverse_pfc(type):

    """
    Returns the pfc location (second layer) of a Type stored in s2k_partypes 'ptt'
    :param type: Has to be a type given in s2k_partypes 'ptt'
    :return: pfc location
    """

    if type.startswith('oct'):
        return type[3:]
    elif type.startswith('ascii'):
        return type[5:]

    for i in ptt: # First Section
        for j in ptt[i]: # Second Section
            if ptt[i][j] == type: # Check for type
                return j

    return False

'''


def user_tm_decoders_func():

    if cfg.has_section('ccs-user_defined_packets'):
        user_tm_decoders = {k: json.loads(cfg['ccs-user_defined_packets'][k])
                                 for k in cfg['ccs-user_defined_packets']}
    else:
        user_tm_decoders = {}

    return user_tm_decoders


# TM formatted
#
#  Return a formatted string containing all the decoded source data of TM packet _tm_
#  @param tm TM packet bytestring
def Tmformatted(tm, separator='\n', sort_by_name=False, textmode=True, UDEF=False):
    sourcedata, tmtcnames = Tmdata(tm, UDEF=UDEF)
    tmtcname = " / ".join(tmtcnames)
    if textmode:
        if sourcedata is not None:
            formattedlist = ['{}:  {} {}'.format(i[2], i[0], none_to_empty(i[1])) for i in sourcedata]
            if sort_by_name:
                formattedlist.sort()
        else:
            formattedlist = []
        return separator.join([Tm_header_formatted(tm)] + [tmtcname] + [100 * "-"] + formattedlist)
    else:
        if sourcedata is not None:
            try:
                formattedlist = [[str(i[2]), str(i[0]), none_to_empty(i[1]),
                                parameter_tooltip_text(i[-1][0])] for i in sourcedata]
            # For variable length packets:
            except:
                formattedlist = [[str(i[2]), str(i[0]), none_to_empty(i[1]),
                                parameter_tooltip_text(i[-1])] for i in sourcedata]
        else:
            formattedlist = [[]]
        return formattedlist, tmtcname


##
#  TM source data
#
#  Decode source data field of TM packet
#  @param tm TM packet bytestring
def Tmdata(tm, UDEF=False, *args):
    tmdata = None
    tmname = None
    tpsd = None
    params = None
    dbcon = scoped_session_idb

    # This will be used to first check if an UDEF exists and used this to decode, if not the ÍDB will be checked
    if UDEF:
        try:
            # with poolmgr.lock:
            header, data, crc = Tmread(tm)
            # data = tm_list[-2]
            st, sst, apid = header.SERV_TYPE, header.SERV_SUB_TYPE, header.APID
            que = 'SELECT pic_pi1_off,pic_pi1_wid from pic where pic_type=%s and pic_stype=%s' % (st, sst)
            dbres = dbcon.execute(que)
            pi1, pi1w = dbres.fetchall()[0]

            pi1val = int.from_bytes(tm[pi1:pi1 + pi1w//8], 'big')
            tag = '{}-{}-{}-{}'.format(st, sst, apid, pi1val)
            user_label, params = user_tm_decoders[tag]
            spid = None
            #o = data.unpack(','.join([ptt[i[4]][i[5]] for i in params]))
            if len(params[0]) == 9: #Length of a parameter which should be decoded acording to given position
                vals_params = decode_pus(data, params)
            else: #Decode according to given order, length is then 11
                vals_params = read_variable_pckt(data, params)

            tmdata = [(get_calibrated(i[0], j[0]), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]
            tmname = ['USER DEFINED: {}'.format(user_label)]

            return tmdata, tmname
        except:
            logger.info('UDEF could not be found, search in IDB')

    try:

        if (tm[0] >> 4) & 1:
            return Tcdata(tm, *args)
        # with poolmgr.lock:
        header, data, crc = Tmread(tm)
        # data = tm_list[-2]
        st, sst, apid = header.SERV_TYPE, header.SERV_SUB_TYPE, header.APID
        que = 'SELECT pic_pi1_off,pic_pi1_wid from pic where pic_type=%s and pic_stype=%s' % (st, sst)
        dbres = dbcon.execute(que)
        pi1, pi1w = dbres.fetchall()[0]
        if pi1 != -1:
            #print(tm[pi1:pi1 + pi1w])
            # pi1val = Bits(tm)[pi1 * 8:pi1 * 8 + pi1w].uint
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
        if tpsd == -1 and params is None:
            que = 'SELECT pcf.pcf_name,pcf.pcf_descr,plf_offby,plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,\
            pcf.pcf_unit,pcf.pcf_pid,pcf.pcf_width FROM plf LEFT JOIN pcf ON plf.plf_name=pcf.pcf_name WHERE \
            plf.plf_spid={} AND pcf_name NOT LIKE "DPTG%" AND pcf_name NOT LIKE "SCTG%" \
            ORDER BY plf_offby,plf_offbi'.format(spid)
            dbres = dbcon.execute(que)
            params = dbres.fetchall()
            #o = data.unpack(','.join([ptt[i[4]][i[5]] for i in params]))
            vals_params = decode_pus(data, params)
            tmdata = [(get_calibrated(i[0], j[0]), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]

        elif params is not None:
            #o = data.unpack(','.join([ptt[i[4]][i[5]] for i in params]))

            if len(params[0]) == 9: #Length of a parameter which should be decoded acording to given position
                vals_params = decode_pus(data, params)
            else: #Decode according to given order, length is then 11
                vals_params = read_variable_pckt(data, params)

            #vals_params = decode_pus(data, params)
            tmdata = [(get_calibrated(i[0], j[0]), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]
        else:
            que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx,pcf.pcf_width,\
            pcf.pcf_unit,pcf.pcf_pid,vpd_pos,vpd_grpsize,vpd_fixrep from vpd left join pcf on \
            vpd.vpd_name=pcf.pcf_name where vpd_tpsd={} AND pcf_name NOT LIKE "DPTG%" \
            AND pcf_name NOT LIKE "SCTG%" ORDER BY vpd_pos'.format(tpsd)
            dbres = dbcon.execute(que)
            params_in = dbres.fetchall()

            vals_params = read_variable_pckt(data, params_in)
            tmdata = [(get_calibrated(i[0], j), i[6], i[1], pidfmt(i[7]), j) for j, i in vals_params]
            # tmdata = [(get_calibrated(i[0], j[0]), i[6], i[1], pidfmt(i[7]), j) for i, j in zip(params, vals_params)]

        if spid is not None:
            dbres = dbcon.execute("SELECT pid_descr FROM pid WHERE pid_spid={}".format(spid))
            tmname = dbres.fetchall()[0]
        else:
            tmname = ['USER DEFINED: {}'.format(user_label)]
    except Exception as failure:
        raise Exception('Packet data decoding failed: ' + str(failure))
        # logger.info('Packet data decoding failed.' + str(failure))
    finally:
        dbcon.close()
    return tmdata, tmname


def decode_pus(tm_data, parameters, decode_tc=False):
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
def read_stream(stream, fmt, pos=None, offbi=0):
    if pos is not None:
        stream.seek(int(pos))

    data = stream.read(csize(fmt, offbi))
    if not data:
        raise BufferError('No data left to read from [{}]!'.format(fmt))

    if fmt == 'I24':
        # x = struct.unpack('>I', b'\x00' + data)[0]
        x = int.from_bytes(data, 'big')
    elif fmt == 'i24':
        # x = struct.unpack('>i', data + b'\x00')[0] >> 8
        x = int.from_bytes(data, 'big', signed=True)
    # for bit-sized unsigned parameters:
    elif fmt.startswith('uint'):
        bitlen = int(fmt[4:])
        # bitsize = (bitlen // 8 + 1) * 8
        bitsize = len(data) * 8
        x = (int.from_bytes(data, 'big') & (2 ** (bitsize - offbi) - 1)) >> (bitsize - offbi - bitlen)
    elif fmt.startswith('oct'):
        x = struct.unpack('>' + fmt[3:], data)[0]
    elif fmt.startswith('ascii'):
        x = struct.unpack('>' + fmt[5:], data)[0]
        x = x.decode()
    elif fmt == timepack[0]:
        x = timecal(data)
    else:
        x = struct.unpack('>' + fmt, data)[0]

    return x

##
#  csize
#
#  Returns the Amount of Bytes for the input format
#  @param fmt Input String that defines the format
#  @param offbi
def csize(fmt, offbi=0):
    if fmt in ('i24', 'I24'):
        return 3
    elif fmt.startswith('uint'):
        return (int(fmt[4:]) + offbi - 1) // 8 + 1
    elif fmt == timepack[0]:
        return timepack[1] - timepack[3]
    elif fmt.startswith('oct'):
        return int(fmt[3:-1]) + offbi
    elif fmt.startswith('ascii'):
        return int(fmt[5:-1]) + offbi
    else:
        return struct.calcsize(fmt)

##
# parameter_ptt_type
#
# Returns the format of the input bytes for TM (list has to be formated the correct way)
# @param parameters Input List of one parameter

def parameter_ptt_type_tm(par):
    if not par[4] in [7,8]:
        return ptt[par[4]][par[5]]
    elif par[4] == 7:
        return 'oct' + str(par[5]) + 's'
    elif par[4] == 8:
        return 'ascii' + str(par[5]) + 's'

##
# parameter_ptt_type
#
# Returns the format of the input bytes for TC (list has to be formated the correct way)
# @param parameters Input List of one parameter

def parameter_ptt_type_tc_read(par):
    if par[2] is None:
        return ptt['SPARE_visible'][par[5]]
    elif par[2] == 7:
        return 'oct' + str(par[3]) + 's'
    elif par[2] == 8:
        return 'ascii' + str(par[3]) + 's'
    else:
        return ptt[par[2]][par[3]]

##
#  Nonetoempty
#
#  Return empty string "" if input is _None_, else return input string
#  @param s Input string
def none_to_empty(s):
    return '' if s is None else s

'''
###### Now in packet_config_PROJECT
##
#  Timecal
#
#  Returns the decoded time for specific Timestamp package
#  @param s Input ByteArray or ByteObject
def timecal(data, string=False):
    data = int.from_bytes(data, 'big')
    coarse = data >> 16
    fine = ((data & 0xffff) >> 1) / 2 ** 15
    if string:
        sync = ['U', 'S'][data & 1]
        return '{:.6f}{}'.format(coarse + fine, sync)
    else:
        return coarse + fine
'''
'''
# Timecal function is now in packet_config_PROJECT
def timecal(bintime, timestr):
    coarse, fine, sync = bintime.unpack(timestr)
    return '{:.6f}'.format(coarse + fine / 2 ** 15)
'''

def Tm_header_formatted(tm, detailed=False):
    '''unpack APID, SEQCNT, PKTLEN, TYPE, STYPE, SOURCEID'''

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


##
#  Parametertooltiptext
#
#  Takes numerical value and returns corresponding hex and decimal values as a string.
#  Intended for parameter view tooltips.

def parameter_tooltip_text(x):
    if isinstance(x, int):
        h = hex(x)[2:].upper()
        if np.sign(x) == -1:
            h = h.replace('x', '-') + '(THIS IS WRONG!)'
    elif isinstance(x, float):
        h = struct.pack('>f', x).hex().upper()
    else:
        h = str(x)
    return 'HEX: {}\nDEC: {}'.format(h, x)


def Tcdata(tm, *args):
    header, data, crc = Tmread(tm)
    st, sst, apid = header.SERV_TYPE, header.SERV_SUB_TYPE, header.APID
    dbcon = scoped_session_idb

    # check if TC contains fixed value parameter for discrimination
    que = 'SELECT ccf_cname,cdf_bit,cdf_value,cpc_ptc,cpc_pfc, cpc_pafref FROM ccf LEFT JOIN cdf ON ccf_cname=cdf_cname ' \
          'LEFT JOIN cpc ON cdf_pname=cpc_pname WHERE ccf_type={} AND ccf_stype={} AND ccf_apid={} AND cdf_eltype="F"'.format(st, sst, apid)

    finfo = dbcon.execute(que).fetchall()
    if finfo:
        cname, offbit, cdfval, ptc, pfc, paf = finfo[0]
        fvalue = read_stream(io.BytesIO(data), ptt[ptc][pfc], pos=offbit // 8)

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
            vals_params = read_variable_pckt(data, params)
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
    try:
        tmtc = pckt[0] >> 4 & 1
        dhead = pckt[0] >> 3 & 1

        if tmtc == 0 and dhead == 1 and (len(pckt) >= TM_HEADER_LEN):
            header = TMHeader()
            header.bin[:] = pckt[:TM_HEADER_LEN]
            data = pckt[TM_HEADER_LEN:-PEC_LEN]
            crc = pckt[-PEC_LEN:]

        elif tmtc == 1 and dhead == 1 and (len(pckt) >= TC_HEADER_LEN):
            header = TCHeader()
            header.bin[:] = pckt[:TC_HEADER_LEN]
            data = pckt[TC_HEADER_LEN:-PEC_LEN]
            crc = pckt[-PEC_LEN:]

        else:
            header = TCHeader()
            header.bin[:P_HEADER_LEN] = pckt[:P_HEADER_LEN]
            data = pckt[P_HEADER_LEN:]
            crc = None

        head_pars = header.bits

    except Exception as err:
        print(' #!# Error unpacking packet: {}\n{}'.format(pckt, err))
        head_pars = None
        data = None
        crc = None

    finally:
        return head_pars, data, crc

##
#  Generate (space separated) hexstring from byte/bitstring
#  @param inbytes   bytestring or bitstring object to be converted
#  @param separator string by which the hex doublettes are joined, default=' '

def prettyhex(inbytes, separator=' '):
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
    while paramid < len(parameters):
        fmt = ptt[parameters[paramid][2]][parameters[paramid][3]]
        if parameters[paramid][2] == 11:
            fmt = fmt[ptype]
            if ptype == 7:  # ptt fmt string for bool not parseable with .read
                fmt = 'uint:8'
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


def read_variable_pckt(tm_data, parameters):
    """
    Read parameters from a variable length packet
    :param tm_data:
    :param parameters:
    :return:
    """
    tms = io.BytesIO(tm_data)
    result = []

    result = read_stream_recursive(tms, parameters, decoded=result)

    return result


def read_stream_recursive(tms, parameters, decoded=None):
    """
    Recursively operating function for decoding variable length packets
    :param tms:
    :param parameters:
    :param decoded:
    :return:
    """

    decoded = [] if decoded is None else decoded

    skip = 0
    for par_idx, par in enumerate(parameters):
        if skip > 0:
            skip -= 1
            continue
        grp = par[-2]

        if grp is None:  # None happens for UDFP, would give error using None
            grp = 0

        fmt = ptt[par[2]][par[3]]
        if fmt == 'deduced':
            if 'ptype' in locals():
                fmt = ptype_values[ptype]
            else:
                print('No format deduced for parameter, aborting.')
                return decoded
        value = read_stream(tms, fmt)

        if par[0] in ptype_parameters:
            ptype = value

        decoded.append((value, par))
        if grp != 0:
            skip = grp
            rep = value
            while rep > 0:
                decoded = read_stream_recursive(tms, parameters[par_idx + 1:par_idx + 1 + grp], decoded)
                rep -= 1

    return decoded


def tc_param_alias_reverse(paf, cca, val, pname=None):
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
    # get name for ParamID if datapool item (CHEOPS only)
    elif pname in ('DPP70004', 'DPP70043'):
        return get_pid_name(pidfmt_reverse(val))
    else:
        return val


def get_pid_name(pid):
    if isinstance(pid, str):
        return pid
    que = 'SELECT pcf_descr from pcf where pcf_pid="{}"'.format(pid)
    dbcon = scoped_session_idb
    fetch = dbcon.execute(que).fetchall()
    dbcon.close()
    if len(fetch) != 0:
        return fetch[0][0]
    else:
        logger.error('Unknown datapool ID: {}'.format(pid))
        return pid


##
#  Format PID from I-DB value to int
def pidfmt(val):
    return int(val - pid_offset) if val is not None else None


def pidfmt_reverse(val):
    return int(val + pid_offset) if val is not None else None


## Parameter calibration
#  Calibrate raw parameter values
#  @param pcf_name PCF_NAME
#  @param rawval   Raw value of the parameter
def get_calibrated(pcf_name, rawval, properties=None, numerical=False, dbcon=None):
    if properties is None:
        dbcon = scoped_session_idb
        que = 'SELECT pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_categ,pcf.pcf_curtx from pcf where pcf_name="%s"' % pcf_name
        dbres = dbcon.execute(que)
        fetch = dbres.fetchall()
        dbcon.close()
        if len(fetch) == 0:
            return rawval[0]

        ptc, pfc, categ, curtx = fetch[0]

    else:
        ptc, pfc, categ, curtx = properties

    try:
        type_par = ptt[ptc][pfc]
    except:
        type_par = None

    if type_par == timepack[0]:
        #return timecal(rawval, 'uint:32,uint:15,uint:1')
        return timecal(rawval)
    elif curtx is None:
        try:
            return rawval if isinstance(rawval, int) else rawval[0]
        except:
            return rawval
    elif curtx is not None and categ == 'N':
        # print('CALIBRATED!')
        return get_cap_yval(pcf_name, rawval)
    elif curtx is not None and categ == 'S':
        if numerical:
            return rawval
        return get_txp_altxt(pcf_name, rawval)


##
#  Numerical calibration
#
#  Calibrate raw parameter values
#  @param pcf_name PCF_NAME
#  @param xval     Raw value of the parameter
def get_cap_yval(pcf_name, xval, properties=None, dbcon=None):
    dbcon = scoped_session_idb
    que = 'SELECT cap.cap_xvals,cap.cap_yvals from pcf left join cap on pcf.pcf_curtx=cap.cap_numbr\
            where pcf.pcf_name="%s"' % pcf_name
    dbres = dbcon.execute(que)
    try:
        xvals, yvals = np.array([x for x in zip(*dbres.fetchall())], dtype=float)
        yval = np.interp(xval, xvals, yvals)
    except IndexError:
        yval = xval
    finally:
        dbcon.close()
    return format(yval, 'g')

##
#  Textual calibration
#
#  Calibrate raw parameter values
#  @param pcf_name PCF_NAME
#  @param alval    Raw value of the parameter
def get_txp_altxt(pcf_name, alval, dbcon=None):
    dbcon = scoped_session_idb
    que = 'SELECT txp.txp_altxt from pcf left join txp on pcf.pcf_curtx=txp.txp_numbr where\
            pcf.pcf_name="%s" and txp.txp_from=%s' % (pcf_name, alval if isinstance(alval, int) else alval[0])
    dbres = dbcon.execute(que)
    try:
        altxt, = dbres.fetchall()[0]
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
def Tmdump(filename, tmlist, mode='hex', st_filter=None, crccheck=False):
    if st_filter is not None:
        tmlist = Tm_filter_st(tmlist, *st_filter)

    if crccheck:
        tmlist = (tm for tm in tmlist if not crccheck(tm))

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
            except:
                txtlist.append(Tm_header_formatted(tm) + '; ' + str(tm[TM_HEADER_LEN:]))
        with open(filename, 'w') as f:
            f.write('\n'.join(txtlist))

##
#  Filter by service (sub-)type
#
#  Return list of TM packets filtered by service type and sub-type
#  @param tmlist List of TM packets
#  @param st     Service type
#  @param        Service sub-type
def Tm_filter_st(tmlist, st=None, sst=None, apid=None, sid=None, time_from=None, time_to=None, eventId=None,
                 procId=None):
    """From tmlist return list of packets with specified st,sst"""
    # stsst=pack('2*uint:8',st,sst).bytes
    # filtered=[tmlist[i] for i in np.argwhere([a==stsst for a in [i[7:9] for i in tmlist]]).flatten()]
    if (st is not None) and (sst is not None):
        tmlist = [tm for tm in tmlist if ((tm[7], tm[8]) == (st, sst))]

    if sid != None:
        tmlist = [tm for tm in list(tmlist) if (tm[TM_HEADER_LEN] == sid or tm[TM_HEADER_LEN] + tm[TM_HEADER_LEN + 1] == sid)] # two possibilities for SID because of  different definition (length) for SMILE and CHEOPS

    if apid != None:
        tmlist = [tm for tm in list(tmlist) if ((struct.unpack('>H', tm[:2])[0] & 2047) == (apid))]

    if eventId != None:
        tmlist = [tm for tm in list(tmlist) if (struct.unpack('>H', tm[TM_HEADER_LEN:TM_HEADER_LEN + 2])[0] == eventId)]

    if procId != None:
        tmlist = [tm for tm in list(tmlist) if
                  (struct.unpack('>H', tm[TM_HEADER_LEN + 2:TM_HEADER_LEN + 4])[0] == procId)]

    if time_from != None:
        tmlist = [tm for tm in list(tmlist) if (time_from <= get_cuctime(tm))]

    if time_to != None:
        tmlist = [tm for tm in list(tmlist) if (get_cuctime(tm) <= time_to)]

    return tmlist

##
#  CRC check
#
#  Perform a CRC check on the _packet_. Returns True if CRC!=0.
#  @param packet TM/TC packet or any bytestring or bitstring object to be CRCed.
def crc_check(packet):
    #if isinstance(packet, (BitArray, BitStream, Bits, ConstBitStream)):
    #    packet = packet.bytes
    return bool(crc(packet))


def get_cuctime(tml):
    cuc_timestamp = None
    if tml is not None:
        if isinstance(tml, bytes):
            return timecal(tml[CUC_OFFSET:CUC_OFFSET + timepack[1]], string=False)
            #ct, ft = struct.unpack('>IH', tml[TM_HEADER_LEN - 7:TM_HEADER_LEN - 1])
            #ft >>= 1
        elif isinstance(tml, packet_config.TMHeaderBits):
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
            logger.warning('get_cuctime: ValueError: the value of finetime is larger than its resolution')
            raise ValueError(
                'get_cuctime: the finetime value {} is larger than its resolution of {}'.format(ft, resolution))

        cuc_timestamp = ct + ft / resolution

    return cuc_timestamp

def get_pool_rows(pool_name, dbcon=None):
    dbcon = scoped_session_storage

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


#  get values of parameter from HK packets
def get_param_values(tmlist=None, hk=None, param=None, last=0, numerical=False):

    if param is None:
        return

    # with self.poolmgr.lock:
    dbcon = scoped_session_idb
    if hk is None:
        que = 'SELECT plf.plf_name,plf.plf_spid,plf.plf_offby,plf.plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_unit,\
                   pcf.pcf_descr,pid.pid_apid,pid.pid_type,pid.pid_stype,pid.pid_descr,pid.pid_pi1_val from pcf\
                   left join plf on pcf.pcf_name=plf.plf_name left join pid on pid.pid_spid=plf.plf_spid\
                   where plf.plf_name="{}"'.format(param)
        dbres = dbcon.execute(que)
        name, spid, offby, offbi, ptc, pfc, unit, descr, apid, st, sst, hk, sid = dbres.fetchall()[0]
        if not isinstance(tmlist, list):
            tmlist = tmlist.filter(DbTelemetry.stc == st, DbTelemetry.sst == sst, DbTelemetry.apid == apid,
                                   func.mid(DbTelemetry.data, SID_OFFSET - TM_HEADER_LEN + 1, SID_SIZE) == struct.pack(SID_FORMAT[SID_SIZE], sid)).order_by(
                DbTelemetry.idx.desc())
            if tmlist is not None:
                if last > 1:
                    tmlist_filt = [tm.raw for tm in tmlist[:last]]
                else:
                    tmlist_filt = [tmlist.first().raw]
            else:
                tmlist_filt = []
        else:
            if (st, sst) == (3, 25):
                tmlist_filt = Hk_filter(tmlist, st, sst, apid, sid)[-last:]
            else:
                tmlist_filt = Tm_filter_st(tmlist, st=st, sst=sst, apid=apid)[-last:]
        #ufmt = ptt['hk'][ptc][pfc]
        ufmt = ptt[ptc][pfc]
    elif hk != 'User defined' and not hk.startswith('UDEF|'):
        if not isinstance(param, int):
            pass  # param=self.get_pid(param)
        que = 'SELECT pid_descr, pid_type,pid_stype,pid_pi1_val,pid_apid,plf.plf_name,plf.plf_spid,plf.plf_offby,plf.plf_offbi,\
                   pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_unit,pcf.pcf_descr,pcf.pcf_pid from pid left join plf on\
                   pid.pid_spid=plf.plf_spid left join pcf on plf.plf_name=pcf.pcf_name where\
                   pcf.pcf_descr="%s" and pid.pid_descr="%s"' % (param, hk)
        dbres = dbcon.execute(que)
        hkdescr, st, sst, sid, apid, name, spid, offby, offbi, ptc, pfc, unit, descr, pid = dbres.fetchall()[0]
        if sid == 0:
            sid = None
        tmlist_filt = Tm_filter_st(tmlist, st=st, sst=sst, apid=apid, sid=sid)[-last:]
        #ufmt = ptt['hk'][ptc][pfc]
        ufmt = ptt[ptc][pfc]

    elif hk.startswith('UDEF|'):
        label = hk.strip('UDEF|')
        hkref = [k for k in user_tm_decoders if user_tm_decoders[k][0] == label][0]
        pktinfo = user_tm_decoders[hkref][1]
        parinfo = [x for x in pktinfo if x[1] == param][0]
        pktkey = hkref.split('-')

        apid = int(pktkey[2]) if pktkey[2] != 'None' else None
        sid = int(pktkey[3])
        name, descr, _, offbi, ptc, pfc, unit, _, bitlen = parinfo

        offby = sum(
            [x[-1] for x in pktinfo[:pktinfo.index(parinfo)]]) // 8 + TM_HEADER_LEN  # +TM_HEADER_LEN for header!
        st = 3
        sst = 25
        tmlist_filt = Hk_filter(tmlist, st, sst, apid, sid)[-last:]
        #ufmt = ptt['hk'][ptc][pfc]
        ufmt = ptt[ptc][pfc]
    else:
        userpar = json.loads(cfg['ccs-plot_parameters'][param])
        if ('SID' not in userpar.keys()) or (userpar['SID'] is None):
            tmlist_filt = Tm_filter_st(tmlist, userpar['ST'], userpar['SST'], apid=userpar['APID'])[-last:]
        else:
            tmlist_filt = Tm_filter_st(tmlist, userpar['ST'], userpar['SST'], apid=userpar['APID'],
                                            sid=userpar['SID'])[-last:]
        offby, ufmt = userpar['bytepos'], userpar['format']
        if 'offbi' in userpar:
            offbi = userpar['offbi']
        else:
            offbi = 0
        descr, unit, name = param, None, None

    bylen = csize(ufmt)
    #print(tmlist_filt)
    #tms = io.BytesIO(tmlist_filt)
    if name is not None:
        que = 'SELECT pcf.pcf_categ,pcf.pcf_curtx from pcf where pcf_name="%s"' % name
        dbres = dbcon.execute(que)
        fetch = dbres.fetchall()
        categ, curtx = fetch[0]
        xy = [(get_cuctime(tm),
               get_calibrated(name, read_stream(io.BytesIO(tm[offby:offby + bylen]), ufmt, offbi=offbi),
                                   properties=[ptc, pfc, categ, curtx], numerical=numerical)) for tm in tmlist_filt]

    else:
        xy = [(get_cuctime(tm), read_stream(io.BytesIO(tm[offby:offby + bylen]), ufmt, offbi=offbi)) for tm in tmlist_filt]
    dbcon.close()
    try:
        return np.array(np.array(xy).T, dtype='float'), (descr, unit)
    except ValueError:
        return np.array(xy, dtype='float, U32'), (descr, unit)


##
#  Filter HK TMs by SID and APID
#  @param tmlist List of TM(3,25) packets
#  @param apid   APID by which to filter
#  @param sid    SID by which to filter
def Hk_filter(tmlist, st, sst, apid=None, sid=None):
    # hks=self.Tm_filter_st(tmlist,3,25)
    # hkfiltered=[tm for tm in hks if ccs.Tmread(tm)[3]==apid and tm[16]==sid]

    if apid in (None, '') and sid not in (0, None):
        return [tm for tm in tmlist if (
                len(tm) > TM_HEADER_LEN and (tm[7], tm[8], tm[TM_HEADER_LEN]) == (st, sst, sid))]
    elif sid not in (0, None):
        return [tm for tm in tmlist if (
                len(tm) > TM_HEADER_LEN and (tm[7], tm[8], struct.unpack('>H', tm[:2])[0] & 0b0000011111111111,
                                             tm[TM_HEADER_LEN]) == (st, sst, apid, sid))]

'''
def calcfmtsize(fmt):
    try:
        return struct.calcsize(fmt)
    except struct.error:
        if fmt in ('i24', 'I24'):
            return 3
        elif fmt.startswith('bit'):
            return int(fmt[3:]) // 8 + 1
        else:
            return 0

def unpack_bytes(data, fmt, offbi=0):
    if fmt == 'I24':
        x = struct.unpack('>I', b'\x00' + data)[0]
    elif fmt == 'i24':
        x = struct.unpack('>i', data + b'\x00')[0] >> 8
    # for bit-sized unsigned parameters:
    elif fmt.startswith('bit'):
        bitlen = int(fmt[3:])
        bitsize = (bitlen // 8 + 1) * 8
        x = (int.from_bytes(data, 'big') & (2 ** (bitsize - offbi) - 1)) >> (bitsize - offbi - bitlen)
    else:
        x = struct.unpack('>' + fmt, data)[0]
    return x
'''
def set_packet_list(packets):
    packet_selection = packets
    return packets

def show_extracted_packet():
    """
    Get packet data selected in poolviewer
    :return:
    """
    pv = dbus_connection('poolviewer', communication['poolviewer'])
    if not pv:
        logger.warning('Could not obtain selected packets from PV!')
        return

    return eval(pv.Functions('selected_packet'))

def packet_selection():
    """Alias for show_extracted_packet call"""
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

    t1 = time.time()
    while (time.time() - t1) < timeout:
        try:
            # module = dbus.SessionBus().get_object(cfg.get('ccs-dbus_names', module_name) + str(instance), '/Messagelistner')
            module = dbus_connection(module_name, instance)
            if module:
                break
            else:
                time.sleep(0.2)
        except dbus.DBusException:
            module = False
            time.sleep(0.2)

    if module:
        return module
    else:
        raise ValueError('No running {} instance found'.format(module_name.upper()))
        return


def connect(pool_name, host, port, protocol='PUS'):  #, return_socket=False, is_server=False, timeout=10, delete_abandoned=False, try_delete=True, pckt_filter=None, options='', drop_rx=False, drop_tx=False):
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

    # None cannot be passed over DBUS
    # if pckt_filter is None:
    #     pckt_filter = False

    # kwarguments = {'return_socket': return_socket, 'is_server': is_server, 'timeout': timeout,
    #                'delete_abandoned': delete_abandoned, 'try_delete': try_delete, 'pckt_filter': pckt_filter,
    #                'options': options, 'drop_rx': drop_rx, 'drop_tx': drop_tx, 'protocol': protocol}

    #TODO: passing the whole kwarg dict over DBUS does not work yet
    pmgr.Functions('connect', pool_name, host, port, {'kwargs': dbus.Dictionary({'protocol': protocol})})
    return


def connect_tc(pool_name, host, port, protocol='PUS'):  #, drop_rx=True, timeout=10, is_server=False, options=''):
    """
    Accessibility function for 'connect_tc' in pus_datapool
    :param pool_name:
    :param host:
    :param port:
    :param drop_rx:
    :param protocol:
    :param timeout:
    :param is_server:
    :param options:
    :return:
    """
    pmgr = get_module_handle('poolmanager')

    # TODO: passing the whole kwarg dict over DBUS does not work yet
    # kwarguments = {'is_server': is_server, 'timeout': timeout, 'options': options, 'drop_rx': drop_rx, 'protocol': protocol}

    pmgr.Functions('connect_tc', pool_name, host, port, {'kwargs': dbus.Dictionary({'protocol': protocol})})
    return

##
#  TC send (DB)
#
#  Send a telecommand over _cncsocket_ to DPU/SEM. This function uses the I-DB to generate the properly formatted PUS packet. The TC is specified with the CCF_DESCR string (case sensitive!) _cmd_, followed by the corresponding number of arguments. The default TC acknowledgement behaviour can be overridden by passing the _ack_ argument.
#  @param cmd       CCF_DESCR string of the TC to be issued
#  @param args      Parameters required by the TC specified with _cmd_
#  @param ack       Override the I-DB TC acknowledment value (4-bit binary string, e.g., '0b1011')
#  @param pool_name Name of pool bound to socket connected to the C&C port
#  @param sleep     Idle time in seconds after the packet has been sent. Useful if function is called repeatedly in a loop to prevent too many packets are being sent over the socket in a too short time interval.
def Tcsend_DB(cmd, *args, ack=None, pool_name=None, sleep=0.2, no_check=False, **kwargs):
    pmgr = dbus_connection('poolmanager', communication['poolmanager'])
    try:
        tc, (st, sst, apid) = Tcbuild(cmd, *args, ack=ack, no_check=no_check, **kwargs)
    except TypeError as e:
        raise e
    if pool_name is None:
        pool_name = pmgr.Variables('tc_name')
        # pool_name = self.poolmgr.tc_name

    # THIS NOW HAPPENS IN PMGR
    # convert to SXI PLM transmission protocol
    #if protocol.upper() == 'PLMSIM':
    #    tc = PLM_PKT_PREFIX_TC_SEND + tc.hex().upper().encode() + PLM_PKT_SUFFIX

    # self.poolmgr.tc_send(pool_name, tc.bytes)
    # self.counters[int(str(apid), 0)] += 1
    # self.logger.info('TC %s,%s sent to %s\n' % (st, sst, apid))
    # time.sleep(sleep)
    # return Tcsend_common(tc.bytes, apid, st, sst, sleep, pool_name)

    return Tcsend_common(tc, apid, st, sst, sleep, pool_name)

##
#  Generate TC
#
#  Create TC bitstring for _cmd_ with corresponding parameters
#  @param cmd  CCF_DESCR string of the requested TC
#  @param args Parameters required by the cmd
#  @param ack  Override the I-DB TC acknowledment value (4-bit binary string, e.g., '0b1011')

def Tcbuild(cmd, *args, sdid=0, ack=None, no_check=False, hack_value=None, **kwargs):
    # with self.poolmgr.lock:
    que = 'SELECT ccf_type,ccf_stype,ccf_apid,ccf_npars,cdf.cdf_grpsize,cdf.cdf_eltype,cdf.cdf_ellen,' \
          'cdf.cdf_value,cpc.cpc_ptc,cpc.cpc_pfc,cpc.cpc_descr,cpc.cpc_pname FROM ccf LEFT JOIN cdf ON ' \
          'cdf.cdf_cname=ccf.ccf_cname LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname ' \
          'WHERE BINARY ccf_descr="%s"' % cmd
    dbcon = scoped_session_idb
    params = dbcon.execute(que).fetchall()
    dbcon.close()

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

        else:
            if hack_value is None:
                values = [tc_param_alias(p[-1], v, no_check=no_check) for p, v in zip_no_pad(params, args)]
            else:
                values = hack_value

            pdata = encode_pus(params, *values)

    return Tcpack(st=st, sst=sst, apid=int(apid), data=pdata, sdid=sdid, ack=ack, **kwargs), (st, sst, apid)


def encode_pus(params, *values, params_as_fmt_string=False):
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
            values.insert(i, tc_param_alias(par[-1], par[7]))

    fmts = [parameter_ptt_type_tc(par) for par in params]

    # deduced parameter types are not supported for TCs
    if 'deduced' in fmts:
        raise NotImplementedError("Deduced parameter types in TCs are not supported! ({})".format(', '.join([p[-2] for p in params if p[8] == 11])))

    try:
        fmt_string = '>'+''.join(fmts)
        return struct.pack(fmt_string, *values)

    except struct.error:
        # proper insertion of spares
        vals_iter = iter(values)
        return b''.join([pack_bytes(fmt, next(vals_iter)) if not fmt.endswith('x') else struct.pack(fmt) for fmt in fmts])

def pack_bytes(fmt, value, bitbuffer=0, offbit=0):

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
        x = struct.pack('>' + fmt[3:], bytes(value))

    elif fmt.startswith('ascii'):
        x = struct.pack('>' + fmt[5:], value.encode())

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
    @param date: date as ISO formatted string
    @param sync: CUC sync flag, if None sync byte is omitted
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
    if not par[-4] in [7, 8]:
        return ptt[par[-4]][par[-3]]
    elif par[-4] == 7:
        return 'oct' + str(par[-3]) + 's'
    elif par[-4] == 8:
        return 'ascii' + str(par[-3]) + 's'

##
#  Acknowledgement
#
#  Get type acknowledgement type for give service (sub-)type and APID from I-DB
#  @param st   Service type
#  @param sst  Service sub-type
#  @param apid APID of TC
def Tcack(cmd):
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
    que = 'SELECT cpc_prfref,cpc_ccaref,cpc_pafref,cpc_descr from cpc where cpc_pname="%s"' % param
    dbcon = scoped_session_idb
    prf, cca, paf, pdesc = dbcon.execute(que).fetchall()[0]
    # this is a workaround for datapool items not being present in PAF/PAS table # DEPRECATED!
    # if param in ['DPP70004', 'DPP70043']:  # DataItemID in TC(211,1)
    #     val = get_pid(val)
    # else:
    #     pass

    if (not no_check) and (prf is not None):
        in_range, error = tc_param_in_range(prf, val, pdesc)
        if not in_range:
            raise ValueError('Range check failed\n{}'.format(error))
        else:
            # subtract offset from PID to be compatible with IASW (CHEOPS only)
            if param in ['DPP70004', 'DPP70043']:
                val -= pid_offset
    else:
        if param in ['DPP70004', 'DPP70043']:
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
#
#  Translates name of Data pool variable to corresponding ID, based on I-DB entry
#  @param paramname Name of the Data pool variables
def get_pid(parnames):
    if isinstance(parnames, int):
        return parnames
    elif not isinstance(parnames, list):
        parnames = [parnames]

    if len(set(parnames)) != len(parnames):
        msg = "Duplicate parameters will be ignored! {}".format(set([p for p in parnames if parnames.count(p) > 1]))
        logger.warning(msg)
        print(msg)

    que = 'SELECT pcf_descr,pcf_pid from pcf where BINARY pcf_descr in ({})'.format(', '.join(['"{}"'.format(p) for p in parnames]))
    dbcon = scoped_session_idb
    fetch = dbcon.execute(que).fetchall()
    dbcon.close()

    if len(fetch) == 1 and len(parnames) == 1:
        return int(fetch[0][1]) if fetch[0][1] is not None else None  # not since IDBv2.1: - 212010000

    elif len(fetch) >= 1:
        descr, pid = zip(*fetch)
        nopcf = [name for name in parnames if name not in descr]
        if nopcf:
            raise NameError("The following parameters are not in the database: {}".format(nopcf))
        nopid = [name for name, p in fetch if p is None]
        if nopid:
            msg = "The following parameters have no PID: {}".format(nopid)
            logger.warning(msg)
            print(msg)
        sort_order = [parnames.index(d) for d in descr]
        descr, pid = zip(*[x for _, x in sorted(zip(sort_order, fetch), key=lambda x: x[0])])
        return descr, pid

    else:
        msg = 'Unknown datapool item(s) {}'.format(parnames)
        # raise NameError(msg)
        logger.error(msg)
        print(msg)
        return None

##
#  Parameter range check
#
#  Check if parameter is within specified range
#  @param prf   PRV_NUMBR
#  @param val   Parameter value
#  @param pdesc Parameter DESCR
def tc_param_in_range(prf, val, pdesc):
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
            print('Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits))
            Notify.Notification.new('Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits)).show()
            return False, 'Parameter %s out of range: %s [valid: %s]' % (pdesc, val, limits)
    elif prfs[0][0] == 'A':
        if val not in [i[2] for i in prfs]:
            valid = ' | '.join([i[2] for i in prfs])
            print('Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid))
            Notify.Notification.new('Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid)).show()
            return False, 'Invalid parameter value for %s: %s [valid: %s]' % (pdesc, val, valid)
    else:
        pass  # TODO: no check for time ranges yet
    return True, ''


##
#  ZIPnoPAD
#
#  Zip parameter-value pairs, skipping padding parameters
#  @param params List of TC parameter properties
#  @param args   List of supplied parameter values
def zip_no_pad(params, args):
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
           sc=None, tmv=PUS_VERSION, pktl=None, chksm=None, **kwargs):

    if pktl is None:
        # pktl = len(data) * 8 + (TC_HEADER_LEN + PEC_LEN - 7)  # 7=-1(convention)+6(datahead)+2(CRC) # len(data) *8, data in bytes has to be bits
        pktl = len(data) + (TM_HEADER_LEN + PEC_LEN - 7)

    if sc is None:
        sc = counters.setdefault(int(str(apid), 0), 1) % 2 ** 14  # wrap around counter to fit in 14 bits
        if sc == 0:
            sc += 1
            counters[int(str(apid))] += 1  # 0 is not allowed for seq cnt

    tm = PUSpack(version=version, typ=typ, dhead=dhead, apid=apid, gflags=gflags, sc=sc, pktl=pktl,
                      tmv=tmv, st=st, sst=sst, sdid=destid, timestamp=timestamp, data=data, **kwargs)
    #tm += data

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
    #global crc
    if pktl is None:
        # pktl = len(data) * 8 + (TC_HEADER_LEN + PEC_LEN - 7)  # 7=-1(convention)+6(datahead)+2(CRC) # len(data) *8, data in bytes has to be bits
        pktl = len(data) + (TC_HEADER_LEN + PEC_LEN - 7)  # 7=-1(convention)+6(datahead)+2(CRC)

    if sc is None:
        sc = counters.setdefault(int(str(apid), 0), 1) % 2 ** 14  # wrap around counter to fit in 14 bits
        if sc == 0:
            sc += 1
            counters[int(str(apid))] += 1  # 0 is not allowed for seq cnt
    tc = PUSpack(version=version, typ=typ, dhead=dhead, apid=int(str(apid), 0), gflags=int(str(gflags), 0),
                      sc=sc, pktl=pktl, tmv=tmv, ack=int(str(ack), 0), st=st, sst=sst, sdid=sdid, data=data, **kwargs)

    if chksm is None:
        #chksm = crc(bytes(tc))
        chksm = crc(tc)

    tc += chksm.to_bytes(2, 'big')  # 16 bit CRC
    #tc += io.BytesIO(bytes(chksm))  # 16 bit CRC

    return tc


##
#  Generate PUS packet
#
#  Create Bitstring conforming to PUS with no CRC appended, for details see PUS documentation
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

    if typ == 1 and dhead == 1:
        header.bits.CCSDS_SEC_HEAD_FLAG = 0
        header.bits.PUS_VERSION = tmv
        header.bits.ACK = ack
        header.bits.SERV_TYPE = st
        header.bits.SERV_SUB_TYPE = sst
        header.bits.SOURCE_ID = sdid

    if typ == 0 and dhead == 1:
        header.bits.SPARE1 = 0
        header.bits.PUS_VERSION = tmv
        header.bits.SPARE2 = tref_stat
        header.bits.SERV_TYPE = st
        header.bits.SERV_SUB_TYPE = sst
        header.bits.DEST_ID = sdid
        ctime, ftime, sync = calc_timestamp(timestamp)
        header.bits.CTIME = ctime
        header.bits.FTIME = ftime
        header.bits.TIMESYNC = sync
        header.bits.SPARE = 0

    return bytes(header.bin) + data

'''
# Available in project specified packet config
def get_cuc_elements(time, sync=0):
    if isinstance(time, (float, int)):
        ctime = int(time)
        ftime = int(time % 1 * 2 ** 15)
    elif isinstance(time, str):
        t = float(time[:-1])
        ctime = int(t)
        ftime = int(t % 1 * 2 ** 15)
        sync = 1 if time[-1].upper() == 'S' else 0
    elif isinstance(time, bytes):
        ctime = int.from_bytes(time[:4], 'big')
        ftime = int.from_bytes(time[-2:], 'big') >> 1
        sync = time[-1] & 1
    return ctime, ftime, sync
'''
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
                ptt[par[-4]][par[-3]][tc_param_alias(FMT_TYPE_PARAM, ptype[ptc], no_check=no_check)])
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
def Tcsend_common(tc_bytes, apid, st, sst, sleep=0.2, pool_name='LIVE'):
    # Note: in general, it is not possible to obtain the OBC time, thus the last packet time is used if available

    global counters #Static Document change a variable only when it is global
    t = get_last_pckt_time(pool_name=pool_name, string=False)
    if t is None:
        t = 0
    Tcsend_bytes(tc_bytes, pool_name)
    # self.Tctostore(tc.bytes,tcpool)
    # get the SSC of the sent packet
    ssc = counters[int(str(apid), 0)]
    # increase the SSC counter
    counters[int(str(apid), 0)] += 1
    #logger.info('TC(%s,%s) sent to APID %s @ %f' % (st, sst, apid, t))
    # More specific Logging format that is compatible with the TST
    log_dict = dict([('st', st),('sst', sst),('ssc', ssc),('apid', apid),('timestamp', t)])
    json_string = '{} {}'.format('#SENT TC', json.dumps(log_dict))
    logger.info(json_string)
    time.sleep(sleep)
    return apid, ssc, t

# get the CUC timestamp of the lastest TM packet
#   @param pool_name: name of the pool
#   @param string: <boolean> if true the CUC timestamp is returned as a string, otherwise as a float
#   @return: <CUC> timestamp or None if failing
def get_last_pckt_time(pool_name='LIVE', string=True, dbcon=None):
    pmgr = dbus_connection('poolmanager', communication['poolmanager'])

    if not pmgr:
        logger.warning('Accessing PMGR failed!')
        return

    # cuc = None
    packet = None
    # fetch the pool_name
    #filename = self.poolmgr.loaded_pools[pool_name].filename
    # pmd = pmgr.Dictionaries('loaded_pools')
    poolname = pmgr.Dictionaries('loaded_pools', pool_name)
    filename = poolname[2] # 3rd entry is the filename of the named tuple, named tuple not possible via dbus
    if not filename:
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
        logger.debug('get_packet_from_pool(): failed to get packets from query')

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

def Tcsend_bytes(tc_bytes, pool_name='LIVE'):
    pmgr = dbus_connection('poolmanager', communication['poolmanager'])
    # Tell dbus with signature = that you send a byte array (ay), otherwise does not allow null bytes
    msg = pmgr.Functions('tc_send', pool_name, tc_bytes, signature='ssay')
    logger.debug(msg)
    #pmgr.Functions('tc_send', pool_name, tc_bytes, ignore_reply=True)
    #self.poolmgr.tc_send(pool_name, tc_bytes)

##
#  Send C&C command
#
#  Send command to C&C socket
#  @param socket_name Name of the pool bound to the socket for CnC/TC communication
#  @param cmd         Command string to be sent to C&C socket
def CnCsend(cmd, pool_name=None):
    #### This function was new arranged
    #Necessary to make it possible to use  socket in poolmanager
    global counters # One can only Change variable as global since we are static

    pmgr = dbus_connection('poolmanager', communication['poolmanager'])
    if pool_name is None:
        pool_name = pmgr.Variables('tc_name')
        #pool_name = self.poolmgr.tc_name
    #cncsocket = self.poolmgr.tc_connections[pool_name] ######Problem with socket element
    packed_data = CnCpack(data=cmd, sc=counters.setdefault(1804, 1))
    #cncsocket.send(self.CnCpack(data=cmd, sc=self.counters.setdefault(1804, 1)).bytes)
    received = pmgr.Functions('socket_send_packed_data', packed_data, pool_name, signature = 'says')
    # logfile.write(logtf(self.tnow()) + ' ' + cmd + ' [CnC]\n')
    if received != None:
        counters[1804] += 1
        received = bytes(received) # convert dbus type to python type
    print('[CNC Response:]' + str(received))

    '''
    received = None
    try:
        received = cncsocket.recv(1024)
        # self.logger.info.write(logtf(self.tnow()) + ' ' + recv[6:].decode() + ' [CnC]\n')
        self.logger.info(received.decode(errors='replace') + ' [CnC]')
        # logfile.flush()
        # s.close()
        self.counters[1804] += 1
    except socket.timeout:
        self.logger.error('Got a timeout')
        self.logger.exception(socket.timeout)
    '''
    return received


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
    header = PHeader()
    header.bits.PKT_VERS_NUM = version
    header.bits.PKT_TYPE = typ
    header.bits.SEC_HEAD_FLAG = dhead
    header.bits.APID = (pid << 4) + cat
    header.bits.SEQ_FLAGS = gflags
    header.bits.PKT_SEQ_CNT = sc
    header.bits.PKT_LEN = len(data) - 1

    return bytes(header.bin) + data.encode()

##
#  Send data to socket
#
#  Send bytestring to specified socket
#  @param data      Bytestring to be sent to socket
#  @param pool_name Name of pool bound to Python socket for CnC/TC communication
def Datasend(data, pool_name):
    pmgr = dbus_connection('poolmanager', communication['poolmanager'])
    pmgr.Functions('tc_send', pool_name, data)
    return

##
#  Limits check
#
#  Check if TM parameter is within specified limits. Return 0 if ok, 1 if out of soft limit, 2 if out of hard limit.
#  @param param OCF_NAME
#  @param val   Parameter value
def Tm_limits_check(param, val, user_limit: dict = None, dbcon=None):
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
    if fmt == 'I':
        num = int(string)
    elif fmt == 'R':
        num = float(string)
    else:
        return string
    return num


def tc_load_to_memory(data, memid, mempos, slicesize=1000, sleep=0.2, ack=None, pool_name='LIVE'):
    """
    Function for loading large data to DPU memory. Splits the input _data_ into slices and sequentially sends them
    to the specified location _memid_, _mempos_ by repeatedly calling the _Tcsend_DB_ function until
    all _data_ is transferred.

    :param data:  Data to be sent to memory. Can be a path to a file or bytestring or struct object
    :param memid: Memory that data is sent to (e.g. 'DPU_RAM')
    :param mempos: Memory start address the data should be patched to
    :param slicesize: Size in bytes of the individual data slices, max=1000
    :param sleep: Idle time in seconds between sending the individual TC packets
    :param ack: Override the I-DB TC acknowledment value (4-bit binary string, e.g., '0b1011')
    :param pool_name: connection through which to send the data
    :return:
    """
    if not isinstance(data, bytes):
        if isinstance(data, str):
            data = open(data, 'rb').read()
        else:
            data = data.bytes

    cmd = get_tc_descr_from_stsst(6, 2)[0]

    slices = [data[i:i + slicesize] for i in range(0, len(data), slicesize)]
    if slicesize > 1000:
        print('SLICESIZE > 1000 bytes, this is not gonna work!')
    slicount = 1

    for sli in slices:
        t1 = time.time()
        parts = struct.unpack(len(sli) * 'B', sli)
        Tcsend_DB(cmd, memid, mempos, len(parts), *parts, ack=ack, pool_name=pool_name)
        sys.stdout.write('%i / %i packets sent\r' % (slicount, len(slices)))
        slicount += 1
        dt = time.time() - t1
        if dt < sleep:
            time.sleep(sleep - dt)

    return len(data)


def get_tc_descr_from_stsst(st, sst):
    res = scoped_session_idb.execute('SELECT ccf_descr FROM mib_smile_sxi.ccf where ccf_type={} and ccf_stype={}'.format(st, sst)).fetchall()
    return [x[0] for x in res]


def bin_to_hex(fname, outfile):
    # bash alternative: hexdump -e '16/1 "%3.2X"' fname > outfile
    bindata = open(fname, 'rb').read()
    buf = prettyhex(bindata)
    with open(outfile, 'w') as fd:
        fd.write(buf)
        print('Wrote {} bytes as HEX-ASCII to {}.'.format(len(bindata), outfile))


def source_to_srec(data, outfile, memaddr=0x40180000, header=None, bytes_per_line=32):
    """
    Generate srec file from source data
    :param data:
    :param outfile:
    :param memaddr:
    :param header:
    :param bytes_per_line:
    :return:
    """

    def srec_chksum(x):
        return sum(bytes.fromhex(x)) & 0xff ^ 0xff

    if bytes_per_line > 250:
        print("Maximum number of bytes per line is 250!")
        return

    if isinstance(data, str):
        with open(data, 'r') as fd:
            textdata = fd.read()
        data = bytes.fromhex(textdata.replace('\n', ' '))

    if header is None:
        fname = outfile.split('/')[-1][-60:]
        header = 'S0{:02X}{:}'.format(len(fname.encode()) + 3, fname.encode().hex().upper())
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

    print('Data written to file: "{}"'.format(outfile))


def get_tc_list(ccf_descr=None):

    if ccf_descr is None:
        cmds = scoped_session_idb.execute('SELECT ccf_cname, ccf_descr, ccf_descr2, ccf_type, ccf_stype, ccf_npars, '
                                          'cpc_descr, cpc_dispfmt, cdf_eltype, cpc_pname, cdf_value, cpc_inter, '
                                          'cpc_radix FROM ccf LEFT JOIN cdf ON cdf.cdf_cname=ccf.ccf_cname '
                                          'LEFT JOIN cpc ON cpc.cpc_pname=cdf.cdf_pname '
                                          'ORDER BY ccf_type, ccf_stype, ccf_cname').fetchall()
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


def get_tm_parameter_list(st, sst, apid, pi1val):
    que = 'SELECT pid_spid, pid_tpsd FROM pid WHERE pid_type={} AND pid_stype={} AND pid_apid={} AND pid_pi1_val={}'.format(st, sst, apid, pi1val)
    spid, tpsd = scoped_session_idb.execute(que).fetchall()[0]

    if tpsd == -1:
        que = 'SELECT plf_name, pcf_descr, plf_offby, pcf_ptc, pcf_pfc FROM plf LEFT JOIN pcf ON plf_name=pcf_name WHERE plf_spid={} ORDER BY plf_offby, plf_offbi'.format(spid)
    else:
        que = 'SELECT vpd_name, pcf_descr, NULL, pcf_ptc, pcf_pfc FROM vpd LEFT JOIN pcf ON vpd_name=pcf_name WHERE vpd_tpsd={} ORDER BY vpd_pos'.format(tpsd)

    res = scoped_session_idb.execute(que).fetchall()

    return res


def get_tm_parameter_info(pname):
    que = 'SELECT ocp_lvalu, ocp_hvalu, ocp_type, txp_from, txp_altxt FROM pcf LEFT JOIN ocp ON pcf_name=ocp_name LEFT JOIN txp ON pcf_curtx=txp_numbr WHERE pcf_name="{}" ORDER BY txp_from, ocp_pos'.format(pname)
    res = scoped_session_idb.execute(que).fetchall()

    return res


def get_tm_id(pcf_descr=None):
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


def get_data_pool_items(pcf_descr=None):
    if pcf_descr is None:
        data_pool = scoped_session_idb.execute('SELECT pcf_pid, pcf_descr, pcf_ptc, pcf_pfc '
                                               'FROM pcf WHERE pcf_pid <> 0').fetchall()

    else:
        data_pool = scoped_session_idb.execute('SELECT pcf_pid, pcf_descr, pcf_ptc, pcf_pfc '
                                               'FROM pcf WHERE pcf_pid <> 0 AND pcf_descr="{}"'.format(pcf_descr)).fetchall()

    scoped_session_idb.close()

    data_pool_dict = {}

    for row in data_pool:
        data_pool_dict.setdefault(row[0:4], []).append(row[5:])

    return data_pool_dict


def get_dp_items(source='mib'):
    fmt = {3: {4: 'UINT8', 12: 'UINT16', 14: 'UINT32'}, 4: {4: 'INT8', 12: 'INT16', 14: 'INT32'}, 5: {1: 'FLOAT'}, 9: {18: 'CUC'}, 7: {1: '1OCT'}}

    if source.lower() == 'mib':
        dp = scoped_session_idb.execute('SELECT pcf_pid, pcf_descr, pcf_ptc, pcf_pfc FROM pcf WHERE pcf_pid IS NOT NULL ORDER BY pcf_pid').fetchall()
        dp_ed = [(*i[:2], fmt[i[2]][i[3]]) for i in dp]
        return dp_ed
    elif source.lower() == 'src':
        return
    else:
        raise NotImplementedError


def make_tc_template(ccf_descr, pool_name='LIVE', preamble='cfl.Tcsend_DB', options='', comment=True, add_parcfg=False):
    try:
        cmd, pars = list(get_tc_list(ccf_descr).items())[0]
    except IndexError:
        raise IndexError('"{}" not found in IDB.'.format(ccf_descr))
    # print(tc_template(cmd, pars, pool_name=pool_name, preamble=preamble, options=options, comment=True))
    return tc_template(cmd, pars, pool_name=pool_name, preamble=preamble, options=options, comment=comment, add_parcfg=add_parcfg)


def tc_template(cmd, pars, pool_name='LIVE', preamble='cfl.Tcsend_DB', options='', comment=True, add_parcfg=False):
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

    pics_path = confignator.get_option('paths', 'ccs')
    pics_path += '/pixmap'

    dialog = Gtk.AboutDialog()
    dialog.set_transient_for(parent)

    dialog.set_program_name('UVIE Central Checkout System')

    dialog.set_copyright('UVIE 01/2022')
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
    Called by the Univie button, option Communication, Used to change the main_application for each project
    (main_instance), also possible to only change main communication for one application
    :param new_main:The new main_application to be called every time in the future
    :param new_main_nbr: The instance of the new main_application
    :param application:The application to change the main communication for, None if chang for all
    :param application_nbr:The instance of :param application
    :param main_instance:The project in which the changes should accure
    :param parentwin:Instance of a Gtk.Window for the Gtk.Dialog, None if called from a command line
    :return:
    """
    save_com = {}
    # Check if a main_instance (project) is given otherwise try to get one, this is a necessary information
    if not main_instance:
        if is_open(application.lower(), application_nbr):
            conn = dbus_connection(application.lower(), application_nbr)
            main_instance = conn.Variables('main_instance')
        else:
            print('Please give a value for "main_instance" (project name)')
            logger.info('No main_instance was given therefore main communication could not be changed')
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
            print('Given application instance or new main communication instance is not open')
            logger.info('Could not change main communication instance to {} for {} since one of these is not '
                        'running'.format(str(new_main)+str(new_main_nbr), str(application)+str(application_nbr)))
    # Change the main communication for the entire project
    elif new_main and new_main_nbr:
        change_main_communication(new_main, new_main_nbr, main_instance)
    else:
        print('Please give a new main application and the instance number')
        logger.info('Not enough information was given to change the main communication')

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


def add_decode_parameter(label=None, format=None, bytepos=None, parentwin=None):
    """
    Add a Parameter which can be used in the User Defined Package, only defined by the format and can therefore only be
    used if the package is decoded in the given order
    :param label: Name of the parameter
    :param format: The format of the Parameter given as the actual String or the location in the ptt definition
    :param bytepos: The offset where a parameter is located in a packet
    :param parentwin: For graphical usage
    :return:
    """

    fmt=None

    if format and label:
        #if label in cfg['ccs-plot_parameters']:
        #    print('Please choose a different name for the parameter, can not exist as plot and decode parameter')
        #    return
        if isinstance(format, str):
            if not ptt_reverse(format):
                if not format in fmtlist.keys():
                    print('Please give a correct Format')
                    return
                else:
                    fmt = fmtlist[format]
            else:
                fmt = format
        elif isinstance(format, list):
            if len(format) == 2:
                try:
                    fmt = ptt[format[0]][format[1]]
                except:
                    print('Give valid location of format')
                    return
            else:
                print('Please give a correct Format Length')
                return

        if bytepos:
            pos = bytepos

    elif parentwin is not None:
        dialog = TmParameterDecoderDialog(parent=parentwin)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            label = dialog.label.get_text()
            #if label in cfg['ccs-plot_parameters']:
            #    print('Please choose a different name for the parameter, can not exist as plot and decode parameter')
            #    dialog.destroy()
            #    return
            pos = dialog.bytepos.get_active_text()
            fmt = dialog.format.get_active_text()
            if fmt in fmtlist:
                fmt = fmtlist[fmt]
                if fmt == 'bit':
                    fmt += str(dialog.bitlen.get_text())

            else:
                fmt += str(dialog.bitlen.get_text())
                if fmt.upper() in fmtlist:
                    fmt = fmtlist[fmt.upper()]
            dialog.destroy()
            #return fmt
        else:
            dialog.destroy()
            return

    else:
        print('Please give a Format')
        return

    # If a position was found the parameter will be stored in user_decoder layer in cfg
    if pos:
        if fmt in fmtlengthlist:
            len = fmtlengthlist[fmt]
        elif fmt.startswith(('bit', 'int', 'oct')):
            len_test = int(fmt[3:])
            if len_test % 8 == 0:
                len = len_test
        elif fmt.startswith('uint'):
            len_test = int(fmt[4:])
            if len_test % 8 == 0:
                len = len_test
        elif fmt.startswith('ascii'):
            len_test = int(fmt[5:])
            if len_test % 8 == 0:
                len = len_test
        else:
            print('Something went wrong')
            logger.info('Error while generating Udef Parameter')
            return

        if len:
            dump = {'bytepos': str(pos), 'bytelen': str(len), 'format': str(fmt)}
            cfg['ccs-user_decoders'][label] = json.dumps(dump)
        else:
            dump = {'bytepos': str(pos), 'format': str(fmt)}
            cfg['ccs-user_decoders'][label] = json.dumps(dump)
    else:
        cfg['ccs-decode_parameters'][label] = json.dumps(('format', str(fmt)))

    cfg.save_to_file()

    if fmt:
        return fmt
    else:
        return


# Let one add an additional User defined Package
# Which can than be decoded
def add_tm_decoder(label=None, st=None, sst=None, apid=None, sid=None, parameters=None, idb_pos=False, parentwin=None):
    """
    Add decoding info for TM not defined in IDB
    @param label: Name of new defined packet
    @param st: Service Type
    @param sst: Sub Service Type
    @param apid:
    @param sid:
    @param parameters: list of parameters
    @param idb_pos: False decode in given order, True decode in given/IBD given positiontm
    @return:
    """

    if label and st and sst and apid:
        tag = '{}-{}-{}-{}'.format(st, sst, apid, sid)

    elif parentwin is not None:
        dialog = TmDecoderDialog(cfg=cfg, logger=logger, parent=parentwin)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            slots = dialog.get_content_area().get_children()[0].get_children()[1].get_children()
            parameters = []
            parameters_name = []
            model = slots[0].get_children()[1].get_child().get_model()
            parameters_name.append([par[1] for par in model])
            parameters = parameters_name[0]
            tag = '{}-{}-{}-{}'.format(dialog.st.get_text(), dialog.sst.get_text(), dialog.apid.get_text(), dialog.sid.get_text())
            label = dialog.label.get_text()
            idb_pos = dialog.idb_position.get_active()
            dialog.destroy()
        else:
            dialog.destroy()
            return
    else:
        print('Please give: label, st, sst and apid')
        return
    dbcon = scoped_session_idb

    if sid is not None:
        parameters = ['Sid'] + parameters
    if None in parameters: # Check if a User defined Parameter was selected
        parameters_descr = []
        parameters_descr.append([par[0] for par in model])
        parameters_descr = parameters_descr[0]

        # The values of the Parameters which are in the database can be found via SQL, the UD parameters have to be looked up in the config file
        params = []
        i =0
        if idb_pos: #Parameters should be decoded by there position given in the IDB or config file

            while i < len(parameters_descr): # Check for each parameter if it is User-defined or IDB
                if parameters[i] is not None: # If parameter is in IDB get its values with SQL Query
                    que = 'SELECT DISTINCT pcf.pcf_name,pcf.pcf_descr,plf_offby,plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,\
                        pcf.pcf_unit,pcf.pcf_pid,pcf.pcf_width FROM plf LEFT JOIN pcf ON plf.plf_name=pcf.pcf_name  \
                        WHERE pcf_name ="%s"' %parameters[i]

                    dbres = dbcon.execute(que)
                    params_value = dbres.fetchall()
                    params.append(params_value[0])
                else: # Parameter is User Defined get the values from the config file
                    try:
                        params_values = json.loads(cfg['ccs-user_decoders'][parameters_descr[i]])
                    except:
                        print('Parameter: {} can only be decoded in given order'.format(parameters_descr[i]))
                        logger.info('Parameter: {} can only be decoded in given order'.format(parameters_descr[i]))
                        return
                    ptt_value = ptt_reverse(params_values['format'])
                    params_value = ['user_defined', parameters_descr[i],
                                    params_values['bytepos'] if 'bytepos' in params_values else None,
                                    params_values['bytelen'] if 'bytelen' in params_values else None,
                                    ptt_value[0], ptt_value[1],
                                    None, None, None]
                    params.append(tuple(params_value))
                i +=1

        else: #Parameters will be decoded in the given order
            while i < len(parameters_descr):  # Check for each parameter if it is User-defined or IDB
                if parameters[i] is not None:  # If parameter is in IDB get its values with SQL Query
                    #que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx, \
                    #        pcf.pcf_width,pcf.pcf_unit,pcf.pcf_pid,vpd_pos,vpd_grpsize,vpd_fixrep from vpd  \
                    #        left join pcf on vpd.vpd_name=pcf.pcf_name WHERE pcf_name ="%s"' % parameters[i]


                    # Most parameters do not have an entry in the vpd table, therefore most of the time the query
                    # would give no result. But what would be needed would be 3 entries with null at the end. This
                    # is done manually here.
                    # Furthermore this means that parameters are only treathed as fixed parameters

                    que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx, \
                            pcf.pcf_width,pcf.pcf_unit,pcf.pcf_pid,null,null,null from pcf \
                            WHERE pcf_name ="%s"' % parameters[i]

                    dbres = dbcon.execute(que)
                    params_value = dbres.fetchall()
                    params.append(params_value[0])

                else:  # Parameter is User Defined get the values from the config file
                    try: # Check where parameter is defined
                        params_values = json.loads(cfg['ccs-user_decoders'][parameters_descr[i]])
                        format = 'bit' + params_values['bytelen']
                        ptt_value = ptt_reverse(format)
                    except:
                        params_values = json.loads(cfg['ccs-decode_parameters'][parameters_descr[i]])
                        ptt_value = ptt_reverse(params_values['format'])

                    params_value = ['user_defined', parameters_descr[i], ptt_value[0],
                                    ptt_value[1], None, None, None, None, None, None, None]

                    params.append(tuple(params_value))
                i += 1

    else:
        if idb_pos: #Parameters should be decoded by there position given in the IDB or config file
            # Check if the User used the PCF Name to describe the parameters or the PCF DESCR
            if 'DPT' in parameters[0]:
                que = 'SELECT DISTINCT pcf.pcf_name,pcf.pcf_descr,plf_offby,plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,\
                    pcf.pcf_unit,pcf.pcf_pid,pcf.pcf_width FROM plf LEFT JOIN pcf ON plf.plf_name=pcf.pcf_name WHERE \
                    pcf_name in {} ORDER BY FIELD({},'.format(tuple(parameters), 'pcf_name')\
                    + str(tuple(parameters))[1:]

                dbres = dbcon.execute(que)
                params = dbres.fetchall()

            else:
                que = 'SELECT DISTINCT pcf.pcf_name,pcf.pcf_descr,plf_offby,plf_offbi,pcf.pcf_ptc,pcf.pcf_pfc,\
                    pcf.pcf_unit,pcf.pcf_pid,pcf.pcf_width FROM plf LEFT JOIN pcf ON plf.plf_name=pcf.pcf_name WHERE \
                    pcf_descr in {} ORDER BY FIELD({},'.format(tuple(parameters), 'pcf_descr')\
                    + str(tuple(parameters))[1:]

                dbres = dbcon.execute(que)
                params = dbres.fetchall()
        else: #Parameters will be decoded in the given order
            # Check if the User used the PCF Name to describe the parameters or the PCF DESCR
            if 'DPT' in parameters[0]:
                #que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx, \
                #        pcf.pcf_width,pcf.pcf_unit,pcf.pcf_pid,vpd_pos,vpd_grpsize,vpd_fixrep from vpd left join pcf on \
                #        vpd.vpd_name=pcf.pcf_name WHERE pcf_name in {} ORDER BY FIELD({},'.format(tuple(parameters),
                #        'pcf_name') + str(tuple(parameters))[1:]

                que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx, \
                        pcf.pcf_width,pcf.pcf_unit,pcf.pcf_pid, null,null,null from pcf WHERE pcf_name in {} \
                        ORDER BY FIELD({},'.format(tuple(parameters), 'pcf_name') + str(tuple(parameters))[1:]

                dbres = dbcon.execute(que)
                params = dbres.fetchall()

            else:
                #que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx, \
                #        pcf.pcf_width,pcf.pcf_unit,pcf.pcf_pid,vpd_pos,vpd_grpsize,vpd_fixrep from vpd left join pcf on \
                #        vpd.vpd_name=pcf.pcf_name WHERE pcf_descr in {} ORDER BY FIELD({},'.format(tuple(parameters),
                #        'pcf_descr') + str(tuple(parameters))[1:]

                que = 'SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_ptc,pcf.pcf_pfc,pcf.pcf_curtx, \
                        pcf.pcf_width,pcf.pcf_unit,pcf.pcf_pid,null,null,null from pcf WHERE pcf_descr in {} \
                        ORDER BY FIELD({},'.format(tuple(parameters), 'pcf_descr') + str(tuple(parameters))[1:]

                dbres = dbcon.execute(que)
                parmas = dbres.fetchall()

    print('Created custom TM decoder {} with parameters: {}'.format(label, [x[1] for x in params]))
    user_tm_decoders[tag] = (label, params)
    dbcon.close()

    if not cfg.has_section('ccs-user_defined_packets'):
        cfg.add_section('ccs-user_defined_packets')
    cfg['ccs-user_defined_packets'][tag] = json.dumps((label, [tuple(x) for x in params]))

    #cfg.save_option('packets', 'testt', [])

    cfg.save_to_file()

    #with open(cfg.source, 'w') as fdesc:
    #    cfg.write(fdesc)
    #del(fdesc)
    #return


# Add a User defined Parameter
def add_user_parameter(parameter=None, apid=None, st=None, sst=None, sid=None, bytepos=None, fmt=None, offbi=None, bitlen=None, parentwin=None):
    # If a Gtk Parent Window is given, open the Dialog window to specify the details for the parameter
    if parentwin != None:
        dialog = AddUserParamerterDialog(parent=parentwin)

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
                if fmt == 'bit':
                    fmt += dialog.bitlen.get_text()
            except:
                dialog.destroy()
                return None

            if not cfg.has_section('ccs-plot_parameters'):
                cfg.add_section('ccs-plot_parameters')
            cfg['ccs-plot_parameters'][label] = json.dumps(
                {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi})

            cfg.save_to_file()

            #with open(cfg.source, 'w') as fdesc:
            #    cfg.write(fdesc)
            dialog.destroy()
            return label, apid, st, sst, sid, bytepos, fmt, offbi

        dialog.destroy()
        return
    # Else If parameter is given as the name of the parameter the others have to exist as well and the parameter is created
    if isinstance(parameter, str):
        label = parameter
        if isinstance(apid, int) and isinstance(st, int) and isinstance(sst, int) and isinstance(bytepos, int) and fmt:
            if fmt == 'bit':
                if bitlen:
                    fmt += bitlen
                else:
                    print('Please give a bitlen (Amount of Bits) if fmt (Parameter Type) is set to "bit"')
                    logger.info('Parameter could not be created, no bitlen was given, while fmt was set to  "bit"')
                    return

            if not isinstance(sid,int):
                sid = int(sid, 0) if sid != None else None
            if not isinstance(offbi, int):
                offbi = int(offbi, 0) if offbi != None else 0
        else:
            print('Please give all neaded parameters in the correct format')
            logger.info('Parameter could not be created, because not all specifications were given correctly')
            return
    # Esle if the Parameter is given as a Dictionary get all the needed informations and create the parameter
    elif isinstance(parameter, dict):
        label = parameter['label']
        apid = parameter['apid']
        st = parameter['st']
        sst = parameter['sst']
        byteps = parameter['bytepos']
        fmt = parameter['fmt']
        if isinstance(label, str) and isinstance(apid, int) and isinstance(st, int) and isinstance(sst, int) and isinstance(bytepos, int) and fmt:
            if fmt == 'bit':
                if bitlen:
                    fmt += bitlen
                else:
                    print('Please give a bitlen (Amount of Bits) if fmt (Parameter Type) is set to "bit"')
                    logger.info('Parameter could not be created, no bitlen was given, while fmt was set to  "bit"')
                    return

            if not isinstance(parameter['sid'], int):
                sid = int(parameter['sid'], 0) if parameter['sid'] else None
            if not isinstance(parameter['offbi'], int):
                offbi = int(parameter['offbi'], 0) if parameter['offbi'] else 0
        else:
            print('Please give all neaded parameters in the correct format')
            logger.info('Parameter could not be created, because not all specifications were given correctly')
            return

    else:
        print('Please give all Parameters correctly')
        return
    # Add the created Parameter to the config file egse.cfg
    if not cfg.has_section('ccs-plot_parameters'):
        cfg.add_section('ccs-plot_parameters')

    cfg['ccs-plot_parameters'][label] = json.dumps(
        {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi})

    cfg.save_to_file()

    #with open(cfg.source, 'w') as fdesc:
    #    cfg.write(fdesc)

    #if is_open('plotter'):
        #plot = dbus_connection('plotter', communication['plotter'])
        #para = (label, apid, st, sst, sid, bytepos, fmt, offbi)
        #plot.Functions('update_user_defined_parameter', para, ignore_reply=True)
        #plot.Functions('update_user_defined_parameter', para)

    return label, apid, st, sst, sid, bytepos, fmt, offbi

# Removes a user defined Parameter
def remove_user_parameter(parname = None, parentwin = None):
    # If a Parameter is given delete the parameter
    if parname and cfg.has_option('ccs-plot_parameters', parname):
        cfg['ccs-plot_parameters'].pop(parname)

        cfg.save_to_file()

        #with open(cfg.source, 'w') as fdesc:
        #    cfg.write(fdesc)
        '''
        if is_open('plotter'):
            plot = dbus_connection('plotter')
            plot.Functions('update_user_defined_parameter',parname , ignore_reply=True)
        '''
        return parname
    # Else if a Parent Gtk window is given open the dialog to select a parameter
    elif parentwin is not None:
        dialog = RemoveUserParameterDialog(cfg, parentwin)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            param = dialog.remove_name.get_active_text()

            cfg['ccs-plot_parameters'].pop(param)

            cfg.save_to_file()

            #with open(cfg.source, 'w') as fdesc:
            #    cfg.write(fdesc)
            dialog.destroy()

            return param

        else:
            dialog.destroy()

        return

    elif parname != None:
        print('Selected User Defined Paramter could not be found please select a new one')
        return

    else:
        return

# Edit an existing user defined Parameter
def edit_user_parameter(parentwin = None, parname = None):

    # If a Existing Parameter is given, open same Window as for adding a parameter, but pass along the existing information
    # Simply overwrite the existing parameter with the new one
    if parname and cfg.has_option('ccs-plot_parameters', parname):
        dialog = AddUserParamerterDialog(parentwin, parname)
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
                if fmt == 'bit':
                    fmt += dialog.bitlen.get_text()
            except ValueError as error:
                print(error)
                dialog.destroy()
                return None

            if not cfg.has_section('ccs-plot_parameters'):
                cfg.add_section('ccs-plot_parameters')
            cfg['ccs-plot_parameters'][label] = json.dumps(
                {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi})

            cfg.save_to_file()

            #with open(cfg.source, 'w') as fdesc:
            #    cfg.write(fdesc)

            dialog.destroy()

            return label, apid, st, sst, sid, bytepos, fmt, offbi
        else:
            dialog.destroy()
            return None

    # Else Open a Window to select a parameter and call the same function again with an existing parameter
    # The upper code will be executed
    else:
        if parname != None:
            print('Selected User Defined Paramter could not be found please select a new one')

        dialog = EditUserParameterDialog(cfg, parentwin)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            param = dialog.edit_name.get_active_text()
            dialog.destroy()
            ret = edit_user_parameter(parentwin, param)
            if ret:
                label, apid, st, sst, sid, bytepos, fmt, offbi = ret
                return label, apid, st, sst, sid, bytepos, fmt, offbi
            else:
                return
        else:
            dialog.destroy()
            return


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
    print(plen, len(spwdata), spwdata.hex())

    # print('> SPW PCKT routing aborted! <')


def setup_gw_spw_routing(gw_hp, gnd_hp, tc_hp=None, spw_head=b'\xfe\x02\x00\x00'):

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
        print(gw, gnd)
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
                                print('# TC:', spw_head + rawtc)
                                msg = pack_plm_gateway_data(spw_head + rawtc)
                                gw.send(msg)

            # t_tc = threading.Thread(target=get_spw_from_plm_gw, args=[gw, tc_s])

            except socket.timeout:
                continue
            except socket.error:
                gnd_s.close()
                tc_s.close()
                print('Closed TM/TC ports. Reopening...')
                break

        time.sleep(1)

    gnd.close()
    tcsock.close()
    gw.close()


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
    # get new session for saving process
    logger.info('Saving pool content to disk...')
    tmlist = list(get_packets_from_pool(pool_name))

    Tmdump(filename, tmlist, mode=mode, st_filter=st_filter, crccheck=False)
    logger.info('Pool {} saved as {} in {} mode'.format(pool_name, filename, mode.upper()))

    return

def get_packets_from_pool(pool_name, indices=[], st=None, sst=None, apid=None, dbsession=None):
    """
    @param pool_name:
    @param indices:
    @param st:
    @param sst:
    @param apid:
    @return:
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

    if len(indices) != 0:
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
    """
    # Add general tst path
    sys.path.append(confignator.get_option('paths', 'tst'))
    # Add all subfolders
    sys.path.append(confignator.get_option('paths', 'tst') + '/codeblockreusefeature')
    sys.path.append(confignator.get_option('paths', 'tst') + '/config_editor')
    sys.path.append(confignator.get_option('paths', 'tst') + '/confignator')
    sys.path.append(confignator.get_option('paths', 'tst') + '/doc')
    sys.path.append(confignator.get_option('paths', 'tst') + '/icon_univie')
    sys.path.append(confignator.get_option('paths', 'tst') + '/images')
    sys.path.append(confignator.get_option('paths', 'tst') + '/log_viewer')
    sys.path.append(confignator.get_option('paths', 'tst') + '/notes')
    sys.path.append(confignator.get_option('paths', 'tst') + '/progress_view')
    sys.path.append(confignator.get_option('paths', 'tst') + '/sketch_desk')
    sys.path.append(confignator.get_option('paths', 'tst') + '/test_specs')
    sys.path.append(confignator.get_option('paths', 'tst') + '/testing_library')
    # insert this to import the tst view.py, not the one in .local folder
    sys.path.insert(0, confignator.get_option('paths', 'tst') + '/tst')

    return

class TestReport:

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
            print('"{}": no such step defined!'.format(str(step)))
            return

    def verify_step(self, step):

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
            print('"{}": no such step defined!'.format(str(step)))
            return

        self.report[self.step_rowid[str(step)]][3] = result

    def export(self, reportdir=None):
        if reportdir is None:
            reportfile = self.specfile.replace('.csv_PIPE', '-TR-{:03d}.csv_PIPE'.format(self.version)).replace('/testspec/', '/testrep/')
        else:
            reportdir += '/' if not reportdir.endswith('/') else ''
            reportfile = reportdir + self.specfile.split('/')[-1].replace('.csv_PIPE', '-TR-{:03d}.csv_PIPE'.format(self.version))

        self.report[1][3] += ' TR-{:03d}, MIB v{}'.format(self.version, self.idb_version)
        self.report[2][3] = time.strftime('%Y-%m-%d')

        buf = '\n'.join([self.delimiter.join(self.report[line]) for line in range(len(self.report))])

        with open(reportfile, 'w') as fd:
            fd.write(buf + '\n')
        print('Report written to {}.'.format(reportfile))


class TestReportGUI(Gtk.MessageDialog):

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
    def __init__(self, parent=None):
        Gtk.Dialog.__init__(self, "Add User Decoder Parameter", parent, 0,
                            buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        self.set_border_width(5)

        box = self.get_content_area()
        ok_button = self.get_action_area().get_children()[0]
        ok_button.set_sensitive(False)

        bytebox = Gtk.HBox()

        self.format = Gtk.ComboBoxText()
        self.format.set_model(self.create_format_model())
        self.format.set_tooltip_text('Format type')
        self.format.connect('changed', self.bitlen_active)
        self.bitlen = Gtk.Entry()
        self.bitlen.set_placeholder_text('BitLength')
        self.bitlen.set_tooltip_text('Length in bits')
        self.bitlen.set_sensitive(False)
        self.bytepos = Gtk.Entry()
        self.bytepos.set_placeholder_text('Byte Offset')
        self.bytepos.set_tooltip_text('(Optional) Including {} ({} for TCs) header bytes, e.g. byte 0 in source data -> offset={}'
                                      .format(TM_HEADER_LEN, TC_HEADER_LEN, TM_HEADER_LEN))

        bytebox.pack_start(self.format, 0, 0, 0)
        bytebox.pack_start(self.bitlen, 0, 0, 0)
        bytebox.pack_start(self.bytepos, 0, 0, 0)
        bytebox.set_spacing(5)

        self.label = Gtk.Entry()
        self.label.set_placeholder_text('Parameter Label')
        self.label.connect('changed', self.check_ok_sensitive, ok_button)

        box.pack_start(self.label, 0, 0, 0)
        box.pack_end(bytebox, 0, 0, 0)
        box.set_spacing(10)

        self.show_all()

    def create_format_model(self):
        store = Gtk.ListStore(str)
        for fmt in fmtlist.keys():
            store.append([fmt])
        for pers in personal_fmtlist:
            store.append([pers])
        return store

    def check_ok_sensitive(self, unused_widget, button):
        if len(self.label.get_text()) == 0:
            button.set_sensitive(False)
        else:
            button.set_sensitive(True)

    def bitlen_active(self, widget):
        if widget.get_active_text() == 'bit*' or widget.get_active_text() not in fmtlist.keys():
            self.bitlen.set_sensitive(True)
        else:
            self.bitlen.set_sensitive(False)


class TmDecoderDialog(Gtk.Dialog):
    def __init__(self, cfg, logger, parameter_set=None, parent=None):
        Gtk.Dialog.__init__(self, "Build User Defined Packet", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        # self.set_default_size(780,560)
        self.set_border_width(5)
        self.set_resizable(True)

        self.logger = logger
        self.cfg = cfg

        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        box = self.get_content_area()

        slots = self.create_view(parameter_set=parameter_set)
        box.pack_start(slots, 1, 1, 0)

        self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        self.ok_button.set_sensitive(False)

        self.show_all()

    def create_view(self, parameter_set=None):
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
        self.label.set_placeholder_text('Label for the current configuration')

        self.sid = Gtk.Entry()
        self.sid.set_placeholder_text('SID')

        self.apid.connect('changed', self.check_entry)
        self.st.connect('changed', self.check_entry)
        self.sst.connect('changed', self.check_entry)
        self.label.connect('changed', self.check_entry)

        entrybox.pack_start(self.label,0, 0, 0)
        entrybox.pack_start(self.apid, 0, 0, 0)
        entrybox.pack_start(self.st, 0, 0, 0)
        entrybox.pack_start(self.sst, 0, 0, 0)
        entrybox.pack_start(self.sid, 0, 0, 0)

        entrybox.set_homogeneous(True)
        entrybox.set_spacing(5)

        decisionbox = Gtk.HBox()

        self.given_poition = Gtk.RadioButton.new_with_label_from_widget(None, 'Local')
        self.given_poition.set_tooltip_text('Decode in given order')
        self.idb_position = Gtk.RadioButton.new_with_label_from_widget(self.given_poition, 'IDB')
        self.idb_position.set_tooltip_text('Decode by parameter position given in IDB')

        decisionbox.pack_start(self.given_poition, 0, 0, 0)
        decisionbox.pack_start(self.idb_position, 0, 0, 0)

        if parameter_set is not None:

            if self.cfg.has_option('ccs-user_defined_packets', parameter_set):
                packet = json.loads(cfg['ccs-user_defined_packets'][parameter_set])
                value = parameter_set
            else:
                for pack in cfg['ccs-user_defined_packets']:
                    pack_val = json.loads(cfg['ccs-user_defined_packets'][pack])
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

        note = Gtk.Label(label="Note: User-Defined_IDB parameter can only be used if IDB order is chosen, "
                               "User-Defined_Local only for Local order")

        box = Gtk.VBox()
        box.pack_start(parameter_view, 1, 1, 5)
        box.pack_start(note, 0,0,0)
        box.pack_start(slotbox, 1, 1, 2)
        box.pack_start(decisionbox, 1, 1, 2)
        box.pack_start(entrybox, 0, 0, 3)

        return box

    def create_param_view(self):
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
        self.parameter_list = Gtk.ListStore(str, str)
        treeview = Gtk.TreeView(self.parameter_list)

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
        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pcf_descr, pcf_name FROM pcf WHERE pcf_name="{}"'.format(name))
        name = dbres.fetchall()
        dbcon.close()
        if len(name) != 0:
            return name[0]
        else:
            return None, None

    def create_parameter_model(self):
        parameter_model = Gtk.TreeStore(str, str)

        dbcon = self.session_factory_idb
        #dbres = dbcon.execute('SELECT pid_descr,pid_spid from pid where pid_type=3 and pid_stype=25')
        dbres = dbcon.execute('SELECT pid_descr,pid_spid from pid order by pid_type,pid_pi1_val')
        hks = dbres.fetchall()
        for hk in hks:
            it = parameter_model.append(None, [hk[0], None])
            dbres = dbcon.execute('SELECT pcf.pcf_descr, pcf.pcf_name from pcf left join plf on\
             pcf.pcf_name=plf.plf_name left join pid on plf.plf_spid=pid.pid_spid where pid.pid_spid={}'.format(hk[1]))
            params = dbres.fetchall()
            [parameter_model.append(it, [par[0], par[1]]) for par in params]
        dbcon.close()
        self.useriter_IDB = parameter_model.append(None, ['User-defined_IDB', None])
        self.useriter_local = parameter_model.append(None, ['User-defined_local', None])
        for userpar in self.cfg['ccs-user_decoders']:
            parameter_model.append(self.useriter_IDB, [userpar, None])
        for userpar in self.cfg['ccs-decode_parameters']:
            parameter_model.append(self.useriter_local, [userpar, None])

        return parameter_model

    def add_parameter(self, widget, listmodel):
        par_model, par_iter = self.treeview.get_selection().get_selected()
        hk = par_model[par_iter].parent[0]
        if par_model[par_iter].parent is None:
            return
        elif hk not in ['User-defined_IDB', 'User-defined_local']:
            param = par_model[par_iter]
            listmodel.append([*param])
        else:
            param = par_model[par_iter]
            listmodel.append([*param])

        return

    def remove_parameter(self, widget, listview):
        model, modeliter = listview.get_selection().get_selected()

        if modeliter is None:
            return

        model.remove(modeliter)
        return

    def check_entry(self, widget):
        if self.apid.get_text_length() and self.st.get_text_length() and self.sst.get_text_length \
                and self.label.get_text_length():
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)



class AddUserParamerterDialog(Gtk.MessageDialog):
    def __init__(self, parent=None, edit=None):
        Gtk.Dialog.__init__(self, "Add User Parameter", parent, 0,
                            buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        self.set_border_width(5)

        box = self.get_content_area()
        ok_button = self.get_action_area().get_children()[0]
        ok_button.set_sensitive(False)

        hbox = Gtk.HBox()

        self.apid = Gtk.Entry()
        self.st = Gtk.Entry()
        self.sst = Gtk.Entry()
        self.apid.set_placeholder_text('APID')
        self.st.set_placeholder_text('Service Type')
        self.sst.set_placeholder_text('Service Subtype')
        self.sid = Gtk.Entry()
        self.sid.set_placeholder_text('SID')
        self.sid.set_tooltip_text('First byte in source data (optional)')

        hbox.pack_start(self.apid, 0, 0, 0)
        hbox.pack_start(self.st, 0, 0, 0)
        hbox.pack_start(self.sst, 0, 0, 0)
        hbox.pack_start(self.sid, 0, 0, 0)
        hbox.set_homogeneous(True)
        hbox.set_spacing(5)

        bytebox = Gtk.HBox()

        self.bytepos = Gtk.Entry()
        self.bytepos.set_placeholder_text('Byte Offset')
        self.bytepos.set_tooltip_text('Including {} ({} for TCs) header bytes, e.g. byte 0 in source data -> offset={}'
                                      .format(TM_HEADER_LEN, TC_HEADER_LEN, TM_HEADER_LEN))
        self.format = Gtk.ComboBoxText()
        self.format.set_model(self.create_format_model())
        self.format.set_tooltip_text('Format type')
        self.format.connect('changed', self.bitlen_active)
        self.offbi = Gtk.Entry()
        self.offbi.set_placeholder_text('Bit Offset')
        self.offbi.set_tooltip_text('Bit Offset (optional)')
        self.bitlen = Gtk.Entry()
        self.bitlen.set_placeholder_text('Bitlength')
        self.bitlen.set_tooltip_text('Length in bits')
        self.bitlen.set_sensitive(False)

        bytebox.pack_start(self.bytepos, 0, 0, 0)
        bytebox.pack_start(self.format, 0, 0, 0)
        bytebox.pack_start(self.offbi, 0, 0, 0)
        bytebox.pack_start(self.bitlen, 0, 0, 0)
        bytebox.set_spacing(5)

        self.label = Gtk.Entry()
        self.label.set_placeholder_text('Parameter Label')
        self.label.connect('changed', self.check_ok_sensitive, ok_button)

        box.pack_start(self.label, 0, 0, 0)
        box.pack_end(bytebox, 0, 0, 0)
        box.pack_end(hbox, 0, 0, 0)
        box.set_spacing(10)

        if edit is not None:
            pars = json.loads(parent.cfg['ccs-plot_parameters'][edit])
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
                if fmt.startswith('bit'):
                    self.bitlen.set_text(fmt.strip('bit'))
                    fmt = 'bit'
                model = self.format.get_model()
                it = [row.iter for row in model if row[0] == fmt_dict[fmt]][0]
                self.format.set_active_iter(it)
            if 'offbi' in pars:
                self.offbi.set_text(str(pars['offbi']))

        self.show_all()

    def create_format_model(self):
        store = Gtk.ListStore(str)
        for fmt in fmtlist.keys():
            store.append([fmt])
        return store

    def check_ok_sensitive(self, unused_widget, button):
        if len(self.label.get_text()) == 0:
            button.set_sensitive(False)
        else:
            button.set_sensitive(True)

    def bitlen_active(self, widget):
        if widget.get_active_text() == 'bit*':
            self.bitlen.set_sensitive(True)
            self.offbi.set_sensitive(True)
        else:
            self.bitlen.set_sensitive(False)
            self.offbi.set_sensitive(False)

class RemoveUserParameterDialog(Gtk.Dialog):
    def __init__(self, cfg, parent=None):
        Gtk.Dialog.__init__(self, "Remove User Defined Parameter", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        self.cfg = cfg

        box = self.get_content_area()

        self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        self.ok_button.set_sensitive(False)


        self.remove_name = Gtk.ComboBoxText.new_with_entry()
        self.remove_name.set_tooltip_text('Parameter')
        self.remove_name_entry = self.remove_name.get_child()
        self.remove_name_entry.set_placeholder_text('Label')
        self.remove_name_entry.set_width_chars(5)
        self.remove_name.connect('changed', self.fill_remove_mask)

        self.remove_name.set_model(self.create_remove_model())

        box.pack_start(self.remove_name, 0, 0, 0)

        self.show_all()

    def create_remove_model(self):
        model = Gtk.ListStore(str)

        for decoder in self.cfg['ccs-plot_parameters'].keys():
            model.append([decoder])
        return model

    def fill_remove_mask(self, widget):
        decoder = widget.get_active_text()

        if self.cfg.has_option('ccs-plot_parameters', decoder):
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)

class EditUserParameterDialog(Gtk.Dialog):
    def __init__(self, cfg, parent=None):
        Gtk.Dialog.__init__(self, "Edit User Defined Parameter", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        self.cfg = cfg

        box = self.get_content_area()

        self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        self.ok_button.set_sensitive(False)

        self.edit_name = Gtk.ComboBoxText.new_with_entry()
        self.edit_name.set_tooltip_text('Parameter')
        self.edit_name_entry = self.edit_name.get_child()
        self.edit_name_entry.set_placeholder_text('Label')
        self.edit_name_entry.set_width_chars(5)
        self.edit_name.connect('changed', self.fill_edit_mask)

        self.edit_name.set_model(self.create_edit_model())

        box.pack_start(self.edit_name, 0, 0, 0)

        self.show_all()

    def create_edit_model(self):
        model = Gtk.ListStore(str)

        for decoder in self.cfg['ccs-plot_parameters'].keys():
            model.append([decoder])
        return model

    def fill_edit_mask(self, widget):
        decoder = widget.get_active_text()

        if self.cfg.has_option('ccs-plot_parameters', decoder):
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)


class ChangeCommunicationDialog(Gtk.Dialog):
    def __init__(self, cfg, main_instance, parent=None):
        """
        This Dialog is used to manage the main_communication in the CCS with a GUI
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
        :return: A Gtk.Box
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
            communication_entry.set_title(name) #Give the boxes names to seperate them
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
    Dialog that pops up at CCS/TST startup to allow for project and IDB configuration
    """

    def __init__(self):
        super(ProjectDialog, self).__init__()

        self.set_title('Project configuration')
        self.set_default_size(300, 100)

        self.project_selection = self._create_project_selection()
        self.idb_selection = self._create_idb_selection()

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

        ccs_path = confignator.get_option('paths', 'ccs')
        ccs_path += '/' if not ccs_path.endswith('/') else ''
        projects = glob.glob(ccs_path + PCPREFIX + '*')

        projects = [p.replace(ccs_path + PCPREFIX, '').replace('.py', '') for p in projects]

        for p in projects:
            project_selection.append(p, p)

        set_as = confignator.get_option('ccs-database', 'project')
        project_selection.set_active_id(set_as)

        return project_selection

    @staticmethod
    def _create_idb_selection():
        idb_selection = Gtk.ComboBoxText()

        mibs = scoped_session_idb.execute('show databases').fetchall()
        mibs = [mib for mib, in mibs if mib.count('mib')]

        for m in mibs:
            idb_selection.append(m, m)

        set_as = confignator.get_option('ccs-database', 'idb_schema')
        idb_selection.set_active_id(set_as)

        return idb_selection

    def _write_config(self, widget, data):
        if data == 1:

            confignator.save_option('ccs-database', 'project', self.project_selection.get_active_text())
            confignator.save_option('ccs-database', 'idb_schema', self.idb_selection.get_active_text())

            self.destroy()
            Gtk.main_quit()

        else:
            self.close()
            sys.exit()
