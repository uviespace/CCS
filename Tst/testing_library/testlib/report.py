#!/usr/bin/env python3
"""
Report - writing log entries
============================
"""
from datetime import datetime
import logging
import collections
import json
import sys

import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl

# create logger
logger = logging.getLogger(__name__)
#now = datetime.now()  # current date and time
#code = now.strftime("%Y%m%d%H%M%S")
#extra = {'id_code': code}
#logger = logging.LoggerAdapter(logger, extra)

import datetime

cmd_test_start_keyword = '#START TEST'
cmd_step_keyword = '#COMMAND STEP'
cmd_step_exception_keyword = 'EXCEPTION IN STEP'
cmd_step_keyword_done = '#STEP DONE'  # ATTENTION! The _done keyword must not contain the start keyword
vrc_test_start_keyword = '#START VERIFICATION'
vrc_step_keyword = '#VERIFICATION FOR STEP'
vrc_step_exception_keyword = 'EXCEPTION IN STEP'
vrc_step_keyword_done = '#VERIFICATION STEP DONE'  # ATTENTION! The _done keyword must not contain the start keyword


def key_word_found(line, key_word):
    """
    Searches for the key_word in the provided string.
    :param str line: string which should be checked for key_word
    :param str key_word: the keyword which is found in a log entry for a command step or a verification step
    :return: True if key_word was found
    :rtype: bool
    """
    assert isinstance(line, str)
    if line.find(key_word) == -1:
        found = False
    else:
        found = True
    return found


def encode_to_json_string(step_number, timestamp, step_version=None, step_result=None, descr=None, run_id=None, step_id=None):
    """
    Make a JSON string out of the step number and timestamp
    :param step_number: number of the step
    :param timestamp: CUC timestamp when the step started
    :return: JSON string
    :rtype: str
    """
    od = collections.OrderedDict([('step', step_number),
                                  ('timestamp', timestamp)])
    if step_version is not None:
        od['version'] = step_version
    if step_result is not None:
        od['result'] = step_result
    if descr is not None:
        od['descr'] = descr
    if run_id is not None:
        od['run_id'] = run_id
    if step_id is not None:
        od['step_id'] = step_id
    json_string = json.dumps(od)
    return json_string

def make_json_string(*args, **kwargs):
    od = {}
    for key, value in kwargs.items():
        od[str(key)] = value
    json_string = json.dumps(od)
    return json_string

def parse_step_from_json_string(line, key_word):
    """
    From a line of the log where a step begins following information is extracted:

    * step number
    * timestamp when the step started (CUC timestamp of the spacecraft)

    This information is extracted by the position in the string.
    :param str line: a line of the log file
    :param str key_word: the keyword which is found in a log entry for a command step or a verification step
    :return: the number of the step and the timestamp when this step started (CUC)
    :rtype: dict
    """
    assert isinstance(line, str)

    keyword_index = line.find(key_word)
    start_bracket = line.find('{', keyword_index)

    if keyword_index != -1:
        try:
            # parse the string into a dictionary
            data = json.loads(line[start_bracket:])
            return data
        except json.decoder.JSONDecodeError:
            logger.error('parse_tc_id_from_json_string: parsing of the TC JSON string failed!')


def command_step_begin(step_param, script_version, pool_name, step_start_cuc, run_id, step_id):
    """
    Builds a string and writes it into the logging file. A keyword is set to enable a machine read out of the log file.
    All information of the step is written in a JSON string.
    :param step_param:
    :param script_version:
    :param pool_name:
    :param step_start_cuc:
    :return:
    """
    #print(step_param)
    logger.info('{} {} {}'.format(cmd_step_keyword,
                                  step_param['step_no'],
                                  encode_to_json_string(step_number=step_param['step_no'],
                                                        timestamp=step_start_cuc,
                                                        step_version=script_version,
                                                        run_id=run_id,
                                                        step_id=step_id,
                                                        descr=step_param['descr'])))
    logger.info(step_param['descr'])
    if 'comment' in step_param:
        if len(step_param['comment']) > 0:
            logger.info('Comment: {}'.format(step_param['comment']))


def command_step_exception(step_param, step_id=None):
    logger.warning('{} {} {}'.format(cmd_step_exception_keyword,
                                  step_param['step_no'], make_json_string(step_id=step_id)))


def command_step_end(step_param, step_end_cuc, step_id):
    logger.info('{} {}\n'.format(cmd_step_keyword_done, encode_to_json_string(step_param['step_no'], step_end_cuc, step_id=step_id)))


def verification_step_begin(step_param, script_version, pool_name, step_start_cuc, run_id, step_id):

    logger.info('{} {} {}'.format(vrc_step_keyword,
                                  step_param['step_no'],
                                  encode_to_json_string(step_number=step_param['step_no'],
                                                        timestamp=step_start_cuc,
                                                        step_version=script_version,
                                                        run_id=run_id,
                                                        step_id=step_id,
                                                        descr=step_param['descr'])))
    logger.info(step_param['descr'])
    if 'comment' in step_param:
        if len(step_param['comment']) > 0:
            logger.info('Comment: {}'.format(step_param['comment']))


def verification_step_exception(step_param, step_id=None):
    logger.warning('{} {} {}'.format(vrc_step_exception_keyword,
                                  step_param['step_no'], make_json_string(step_id=step_id)))


def verification_step_end(step_param, step_result, step_end_cuc, step_id):
    logger.info('{} {} {}'.format(vrc_step_keyword_done,
                                  step_param['step_no'],
                                  encode_to_json_string(step_number=step_param['step_no'],
                                                        timestamp=step_end_cuc,
                                                        step_id=step_id,
                                                        step_result=step_result)))
    if step_result is True:
        logger.info('Verification for step {} was passed successful. +++ OK +++\n'.format(step_param['step_no']))
    else:
        logger.warning('Verification for step {} failed.\n'.format(step_param['step_no']))


class StepSummary:
    has_exception = False

    def __init__(self, step_number, result=None):
        self.step = step_number
        self.result = result

    def had_exception(self):
        self.has_exception = True
# --------------------------------------------
# Command log output

def write_log_step_header(step_param, pool_name, step_start_cuc):
    logger.info('STEP {} (starting from {})'
             .format(step_param['step_no'], step_start_cuc))
    logger.info(step_param['descr'])
    if 'comment' in step_param:
        if len(step_param['comment']) > 0:
            logger.info('Comment: {}'.format(step_param['comment']))


def write_log_step_footer(step_param, step_result):
    if step_result is True:
        logger.info('Step {} was passed successful. +++ OK +++'.format(step_param['step_no']))
    else:
        logger.warning('Step {} failed.'.format(step_param['step_no']))

def write_log_test_header(test, pool_name=None):
    logger.info('-------------------------------------------------------------------------------')
    #logger.info('#Start Test: {}\n\t\t\t\t\tversion {}\n\t\t\t\t\tpoolname = {}\n\t\t\t\t\tCUC-timestamp of test '
    #         'start = {}\n\t\t\t\t\tlocal time = {}'
    #         .format(test.id, test.version, pool_name, cfl.get_last_pckt_time(pool_name=pool_name, string=False),
    #                 datetime.datetime.now().isoformat()))
    date_time = datetime.datetime.now().isoformat()
    logger.info('{} {}'.format(cmd_test_start_keyword, make_json_string(test_name=test.id,
    #                                                    version=test.version,
                                                        pool_name=pool_name,
                                                        cuc_start_time=cfl.get_last_pckt_time(pool_name=pool_name, string=False),
                                                        local_start_time=date_time,
                                                        run_id=test.run_id)))

    logger.info('#Description: {} \n'.format(test.description))
    if test.comment:
        logger.info('Comment: {}'.format(test.comment))


def write_log_test_footer(test):
    logger.info('Results:')
    logger.info('~~~~~~~~~~~~~~~~~~~~~~~~~')
    # no test_results
    successful_steps = 0
    if len(test.step_results) < 1:
        if test.precond_ok is False:
            logger.info('Precondition not fulfilled!')
        logger.info('No steps were ran successfully.')
        test.test_passed = False
    else:
        for item in test.step_results:
            if item.result is not True:
                if item.has_exception:
                    logger.info('{} step FAILED - exception in {}!'.format(test.id, item.step))
                else:
                    logger.info('{} step {} FAILED!'.format(test.id, item.step))
                test.test_passed = False
            else:
                successful_steps += 1
                logger.info('{} step {} OK'.format(test.id, item.step))
    logger.info('~~~~~~~~~~~~~~~~~~~~~~~~~')
    if test.test_passed is not False and successful_steps == test.number_of_steps:
        logger.info('Test {} OK {}/{} steps ran sucessfully'.format(test.id, successful_steps, test.number_of_steps))
    else:
        logger.info('Test {} FAILED! {}/{} steps ran sucessfully'.format(test.id, successful_steps, test.number_of_steps))
    logger.info('-------------------------------------------------------------------------------\n\n\n')
    return successful_steps


def print_data_tuple(tm_packets):
    if not isinstance(tm_packets, list):
        tm_packets = [tm_packets]
    for packet in tm_packets:
        if isinstance(packet, bytes):
            data = cfl.Tmdata(packet)[0]
        elif isinstance(packet, tuple):
            data = packet[1][0]
        else:
            data = None
            logger.warning('The format of this TM packet is not known')
        if data is not None:
            for item in data:
                name = item[2]
                value = item[0]
                logger.debug('{} = {}'.format(name, value))


def print_event_data_tuple(tm_packets):
    if not isinstance(tm_packets, list):
        tm_packets = [tm_packets]
    for packet in tm_packets:
        if isinstance(packet, bytes):
            data = cfl.Tmdata(packet)[0]
        elif isinstance(packet, tuple):
            data = packet[1][0]
        else:
            data = None
            logger.warning('The format of this TM packet is not known')
        if data is not None:
            event_id = data[0][0]
            src = data[1][0]
            dest = data[2][0]
            logger.debug('Event {}: {} -> {}'.format(event_id, src, dest))


def write_precondition_outcome(result):
    """
    Logs the outcome of the establish_preconditions function in a test script.
    :param result: bool
        True if all precondition could be established successfully
    """
    if result is True:
        logger.info('Preconditions are fulfilled.\n')
    else:
        logger.warning('Preconditions are NOT fulfilled.\n')

def write_postcondition_outcome(result):
    """
    Logs the outcome of the establish_postconditions function in a test script.
    :param result: bool
        True if all postcondition could be established successfully
    """
    if result is True:
        logger.info('Postconditions are fulfilled.\n')
    else:
        logger.warning('Postconditions are NOT fulfilled.\n')

