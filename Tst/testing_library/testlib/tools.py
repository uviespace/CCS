#!/usr/bin/env python3
"""
Tools
=====
"""
import logging
import os
import configparser
import math
import sys

import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl

# create a logger
logger = logging.getLogger(__name__)

# ToDo: Organisation of modules and functions:
# How to structure functions? Possible sections:
# * I-DB access (instrument database)  # ToDo: idb.py
# * access of TM/TC data pool (core functions of TM/TC handling) # ToDo: packets.py
# **  database queries
# **  unpacking TM/TC packets
# **  packing TC packets
# * TM/TC handling (high level, this functions should use core functions for database interaction)# ToDo: tm.py
# **  fetching TMs: last TM, all TMs, TMs in a specific time interval [reftime, endtiem], [reftime, now], [now, endtime]
# ***   events
# ***   housekeeping / specific parameters
# ***   acknowledgement
# **  functions for specific TC's# ToDo: tc.py
# ***    there are a lot of them
# * creating log files# ToDo: report.py
# * overall tools, like comparison# ToDo: tools.py
# * simulator handling (turning on/off)# ToDo: sim.py
# ToDo: These sections should be separated in order to make unit-testing easy and a good readability and understanding.


# def read_config():
#     print(os.getcwd())
#     file_path = None
#     if os.path.isfile(os.path.abspath('../egse.cfg')):
#         file_path = '../egse.cfg'
#     elif os.path.isfile(os.path.abspath('egse.cfg')):
#         file_path = 'egse.cfg'
#     try:
#         #logger.info('read_config: Reading configuration file: {}'.format(os.path.abspath(file_path)))
#         config = config.Config(file_path=file_path)
#         return config
#     except Exception as exception:
#         pass
#         #logger.error('Could not find the configuration file: {}'.format(os.path.abspath(file_path)))
#         #logger.exception(exception)


# def read_config_file():
#     config = None
#     # load the config file
#     configuration_file = os.path.realpath('egse.cfg')
#     if os.path.isfile(os.path.abspath(configuration_file)):
#         try:
#             config = configparser.ConfigParser()
#             config.read(configuration_file)
#             config.source = configuration_file
#         except Exception as ex:
#             logger.critical('Configuration file {} could not be read!'.format(configuration_file))
#             logger.exception(ex)
#     else:
#         configuration_file = os.path.realpath('../egse.cfg')
#         if os.path.isfile(os.path.abspath(configuration_file)):
#             try:
#                 config = configparser.ConfigParser()
#                 config.read(configuration_file)
#                 config.source = configuration_file
#             except Exception as ex:
#                 logger.critical('Configuration file {} could not be read!'.format(configuration_file))
#                 logger.exception(ex)
#         else:
#             logger.error('Could not find the configuration file: {}'.format(os.path.abspath(configuration_file)))
#     return config


# read the path for the logging files from the configuration file egse.cfg.
# if the directory does not exist it is created.
def get_path_for_testing_logs():
    # fetch the path from the project config file
    # path = cfl.cfg.get('LOGGING', 'test_run')
    path = confignator.get_config().get('tst-logging', 'test_run')
    # create the directory for the logging files if it does not exist
    os.makedirs(path, mode=0o777, exist_ok=True)
    return path


# comparison functions: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def assert_equal(expected, actual, desc=None):
    # Check if the expected value equals the actual value
    result = (expected == actual)
    logger.debug('Assertion: {} -> {}: expected {} , actually is {}'.format(result, desc, expected, actual))
    return result


def assert_true(value, desc=None):
    return assert_equal(expected=True, actual=value, desc=desc)


def assert_false(value, desc=None):
    return assert_equal(expected=False, actual=value, desc=desc)


def assert_unequal(expected, actual, desc=None):
    result = (expected != actual)
    logger.debug('Assertion: {} -> {}: expected {} , actually is {}'.format(result, desc, expected, actual))
    return result


def assert_smaller(limit, actual, desc=None):
    result = actual < limit
    logger.debug('Assertion: {} -> {}: should be smaller than {}, actually is {}'.format(result, desc, limit, actual))
    return result


def make_step_summary(param, result, has_exception=False):
    if isinstance(param, dict):
        step_number = param['step_no']
    else:
        step_number = param
    dictionary = {
        'step': step_number,
        'result': result
    }
    if has_exception is True:
        dictionary['exception'] = True
    return dictionary


def convert_apid_to_int(apid):
    """ Convert the APID into a integer.
    If the APID is given as hexagonal number like '0x14C' this function converts it to an integer.
    If the APID is a string like '332', a integer is returned.
    For stings that are not valid a ValueError is raised
    
    :param apid: str or int
        if the APID is a string, it is converted to an integer
    :return: int
        the APID as integer or None
    """
    assert isinstance(apid, int) or isinstance(apid, str)

    res = None
    if isinstance(apid, str):
        try:
            if 'x' in apid:
                res = int(apid, 16)
            else:
                res = int(apid)
        except ValueError as err:
            logger.exception(err)
    if isinstance(apid, int):
        res = apid
    if res is None:
        logger.error('convert_apid_to_int: failed to convert the APID {} into an integer'.format(apid))

    return res


# Stripping the last char from the hexadezimal apid
#   @param apid: <int> application process identifier
#   @result: <int> PID, None if no valid apid is provided
def extract_pid_from_apid(apid):
    result = None
    """ Since commands ('0x14C' = 332 and '0x3CC' = 972) are not in the pid table, this check is not used
    # query for the existing apids
    self.c.execute('SELECT PID_APID FROM dabys_mib_cheops.pid')
    pid_table = self.c.fetchall()
    pid_table = set(pid_table)
    valid_apids = []
    for k in pid_table:
        valid_apids.append(k[0])

    if apid in valid_apids:
        # convert...
    """
    # if the apid is provided as a string try to convert it to a integer
    if isinstance(apid, str):
        try:
            apid = int(apid)
        except ValueError as error:
            try:
                apid = int(apid, 16)
            except ValueError as error:
                logger.exception(error)

    if isinstance(apid, int):
        # convert the apid into hexadecimal system and slice the last character (=PID), then convert it back to an int
        apid_as_hex = hex(apid)
        pid_as_hex = apid_as_hex[:4]
        pid_as_dez = int(pid_as_hex, 16)
        result = pid_as_dez

    return result


def print_apids():
    apids = [
        {'pid': '0x14', 'pcat': '0xC', 'apid': '0x14C', 'desc': 'All commands to IFSW'},
        {'pid': '0x14', 'pcat': '0x1', 'apid': '0x141', 'desc': 'Reports from IFSW of type: (1,x), (5,x), (6,x)'},
        {'pid': '0x14', 'pcat': '0x2', 'apid': '0x142', 'desc': 'Other IFSW reports not already assigned to the other APIDs'},
        {'pid': '0x14', 'pcat': '0x3', 'apid': '0x143', 'desc': 'Service 196 reports from IFSW (this in particular includes the centroiding report)'},
        {'pid': '0x14', 'pcat': '0x4', 'apid': '0x144', 'desc': 'Service 13 reports from IFSW (this in particular includes the science data)'},
        {'pid': '0x3C', 'pcat': '0xC', 'apid': '0x3CC', 'desc': 'All commands to the SEM'},
        {'pid': '0x3C', 'pcat': '0x1', 'apid': '0x3C1', 'desc': 'All reports from the SEM'}
    ]
    print('APID(hex)\tAPID(int)\tdescription\tPID\tPCAT')
    for i in apids:
        print('{}\t{}\t{}\t{}\t{}'.format(i['apid'], int(i['apid'], base=16), i['desc'], i['pid'], i['pcat']))


# calculate the difference between two CUC-timestamps. The arguments can be CUC timestamp or a TM packet
#   @param value1: <float> or <tmpacket>
#   @param value2: <float> or <tmpacket>
#   @return: <float>
def get_cuc_diff(value1, value2):
    if not isinstance(value1, float):  # if value1 is a TM packet
        value1 = cfl.get_cuctime(value1)
    if not isinstance(value2, float):  # if value2 is a TM packet
        value2 = cfl.get_cuctime(value2)
    difference = math.fabs(value2-value1)
    return difference


# Check if the entry is equal to the provided value
#   @param entry: <tuple>: consisting out of key-value pairs <dict>, the housekeeping CUC timestamp <CUC>,
#                 housekeeping name <str>
#   @param key_value: <dict>: key value pair: {'name_of_the_entry': 'expected_value of the entry'}
#   @param return: <boolean> returns True is the expected value of the entry matches the actual value
def entry_is_equal(entry, key_value):
    """
    Checks if the values of data-pool entries are as expected. If the expected value of an entry is None, this entry is
    considered as matching for the evaluation of the success of the function.

    :param (tuple) entry:    consisting out of key-value pairs <dict>, the housekeeping CUC timestamp <CUC>,
                             housekeeping name <str>
    :param (dict) key_value: is a dictionary of key value pairs: {'name_of_the_entry': 'expected_value of the entry'}

    :return: True is the expected value of the entry matches the actual value
    :rtype: bool
    """
    result = False

    def compare_entry(dictionary, key_value_pair):
        matches = False
        found_false = False
        if isinstance(key_value_pair, dict):
            keys = key_value_pair.keys()
            for key in keys:
                expected_value = key_value_pair[key]
                # check if the entry of the house keeping has the expected value
                if key in dictionary:
                    if expected_value is None:
                        logger.info('{} = {} (no value expected)'.format(key, dictionary[key], expected_value))
                        matches = True
                    else:
                        logger.info('{} = {} (expected {})'.format(key, dictionary[key], expected_value))
                        if dictionary[key] == expected_value:
                            matches = True
                        else:
                            found_false = True
        else:
            logger.error('entry_is_equal: arg key_value is not a dict')
        if found_false is True:
            matches = False
        return matches

    if isinstance(entry, tuple):
        entries = entry[0]
        if isinstance(entries, dict):
            result = compare_entry(dictionary=entries, key_value_pair=key_value)
        else:
            logger.error('entry_is_equal: arg entry does not contain a dict on the 0th position')
    elif isinstance(entry, dict):
        result = compare_entry(dictionary=entry, key_value_pair=key_value)
    else:
        logger.error('entry_is_equal: arg entry is not a tuple')
    return result


# checks if the values of data entries are smaller than the expected value
#   @param to_check: <dict> or <tuple>: the actual entries and values
#   @param expected: <dict>: dictionary of the expected values
#   @return: <boolean>: True if all values are smaller than the expected value
def entry_is_smaller(to_check, expected):
    result = False
    # check if the input is of the correct type
    assert isinstance(to_check, dict) or isinstance(to_check, tuple), logger.error('Got {}'.format(type(to_check)))
    assert isinstance(expected, dict), logger.error('Got {}'.format(type(expected)))

    # checks if actual entries are smaller than the expected value
    #   @param dictionary: <dict>: entries which should be compared
    #   @param key_value_pair: <dict>: values which are expected
    #   @return: <boolean>
    def is_smaller(actual_entries, exp_key_value_pair):
        smaller = False
        found_false = False
        # check argument types
        assert isinstance(actual_entries, dict), logger.error('Got {}'.format(type(to_check)))
        assert isinstance(exp_key_value_pair, dict), logger.error('Got {}'.format(type(actual_entries)))
        to_check_keys = actual_entries.keys()
        for key in to_check_keys:
            assert isinstance(actual_entries[key], int) or isinstance(actual_entries[key], float), logger.error(
                'Got {}'.format(type(actual_entries[key])))
        expected_keys = exp_key_value_pair.keys()
        for key in expected_keys:
            assert type(actual_entries[key]) is int or float, logger.error('Got {}'.format(type(exp_key_value_pair[key])))

        if isinstance(exp_key_value_pair, dict):
            keys = exp_key_value_pair.keys()
            for key in keys:
                expected_value = exp_key_value_pair[key]
                # check if the entry of the house keeping has the expected value
                if key in actual_entries:
                    logger.info('{} = {} (expected to be < {})'.format(key, actual_entries[key], expected_value))
                    if actual_entries[key] < expected_value:
                        smaller = True
                    else:
                        found_false = True
        else:
            logger.error('entry_is_equal: arg key_value is not a dict')
        if found_false is True:
            smaller = False
        return smaller

    # convert the the entries to check into a dictionary and compare them the expected values
    if isinstance(to_check, tuple):
        entries = to_check[0]
        if isinstance(entries, dict):
            result = is_smaller(actual_entries=entries, exp_key_value_pair=expected)
        else:
            logger.error('entry_is_equal: arg entry does not contain a dict on the 0th position')
    elif isinstance(to_check, dict):
        result = is_smaller(actual_entries=to_check, exp_key_value_pair=expected)
    else:
        logger.error('entry_is_equal: arg entry is not a tuple')
    return result


def log_dictionary_entries(par_dict):
    """
    Logging the entries of a dictionary.
    :param par_dict: dict
        Dictionary of whose entries should be logged.
    """
    assert isinstance(par_dict, dict) or par_dict is None
    if par_dict is not None:
        for key_name in par_dict:
            logger.info('{}: {}'.format(key_name, par_dict[key_name]))
    else:
        logger.debug('log_dictionary_entries: no dict was provided')


def compare_content(data_a, data_b):
    """
    Comparing the content of the data fields.
    Expecting lists of parameter tuples.
    :param data_a: list
        List of parameter tuples
    :param data_b: list
        List of parameter tuples
    :return: bool
        True if the content are equal
    """
    assert isinstance(data_a, list)
    assert isinstance(data_b, list)

    the_same = None

    # check if the both have the same number of entries
    equal_length = None
    len_data_a = len(data_a)
    len_data_b = len(data_b)
    if len_data_a == len_data_b:
        equal_length = True

    # compare the entries (assuming that the order in the list is the same)
    equal_entries = None
    for i in range(len(data_a)):
        data_a_entry = data_a[i]
        data_b_entry = data_b[i]
        if data_a_entry != data_b_entry:
            equal_entries = False
            print('entries at index {} are not equal:'.format(i))
            print('{}'.format(data_a_entry))
            print('{}'.format(data_b_entry))
            break
        else:
            equal_entries = True

    if equal_length and equal_entries:
        the_same = True

    return the_same
