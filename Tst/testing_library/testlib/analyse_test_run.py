#!/usr/bin/env python3
"""
Gives a pretty print overview or an output file of the outcome of a test run.
For this the log files of the executed Command and Verification scripts are used.
"""
import confignator
import csv
import datetime
import os
from os import listdir
from os.path import isfile, join
import os, os.path
import errno
import logging

import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()

import toolbox
from testlib import analyse_verification_log
from testlib import analyse_command_log

test_name = 'test'  # Name of the test that should be analysed
run_id = '20210722123605'  # Run ID that should be analysed or NONE for whole file

cmd_log_file_end = '_command.log'
vrc_log_file_end = '_verification.log'
basic_log_file_path = confignator.get_option('tst-logging', 'test_run')
basic_output_file_path = confignator.get_option('tst-logging', 'output-file-path')
basic_json_file_path = confignator.get_option('tst-paths', 'tst_products')
output_file_header = ['Item', 'Description', 'Verification', 'TestResult']

def save_result_to_file(test_name, log_file_path=None, output_file_path=None, json_file_path=None, run_id=None, test_report=None, logger=False):
    """
    Analyses the command and verification log file and creates a txt output table
    :param str test_name: the name of the test and of its log files
    :param str log_file_path: Path to the log files, None if basic one should be used
    :param str output_file_path: Path were the output file should be saved
    :param str json_file_path: Path to the json file, None if basic one should be used
    :param str run_id: Output only for specific Run defined by Run ID, None use whole file
    :param str test_report: The Test Report number as a string, end of the output file name
    :param str logger: A logger
    """
    # Logger is only used, if function is called from a different file (Progres Viewer), therefore a logger and a file
    # are already set up, if file is called standalone, messages are printed
    if logger:
        logger = logging.getLogger(__name__)
        logger.setLevel(level=logging.DEBUG)
        console_hdlr = toolbox.create_console_handler(hdlr_lvl=logging.DEBUG)
        logger.addHandler(hdlr=console_hdlr)

    # Get the given file paths or use the basic ones specified in the tst.cfg file
    if not log_file_path:
        log_file_path = basic_log_file_path
    if not output_file_path:
        output_file_path = basic_output_file_path
    if not json_file_path:
        json_file_path = basic_json_file_path + '/' + test_name + '.json'

    cmd_log_file = log_file_path + '/' + test_name + cmd_log_file_end
    vrc_log_file = log_file_path + '/' + test_name + vrc_log_file_end

    # Get all the steps and verification steps from the respective log files
    cmd_steps = analyse_command_log.get_steps_and_commands(cmd_log_file)
    vrc_steps = analyse_verification_log.get_verification_steps(vrc_log_file)

    cmd_steps_filtered = []
    vrc_steps_filtered = []

    # Filter for a specific run
    if run_id:
        for step in cmd_steps:
            if step['run_id'] == run_id:
                cmd_steps_filtered.append(step)

        for step in vrc_steps:
            if step['run_id'] == run_id:
                vrc_steps_filtered.append(step)

        cmd_steps = cmd_steps_filtered
        vrc_steps = vrc_steps_filtered

    # Get the general run information/description/precon/postcon and the pre/post that do not belong to a step
    # Is already filtered for a specific run if one was given
    general_run_infos, precon_info, postcon_info = analyse_command_log.get_general_run_info(cmd_log_file, run_id=run_id)

    # Give the output file its name, consits of test name, the specification nbr (version)
    name_start = '{}-TS-{}-TR-'.format(test_name, cmd_steps[0]['version'])

    # Check if output folder exists otherwise make it
    if not os.path.isdir(output_file_path):
        os.makedirs(output_file_path)

    # If Test Report Integer is not given, check all existing files and use the next higher one
    if not test_report:
        prev_test_reports = []
        for file_name in listdir(output_file_path):
            if file_name.startswith(name_start):
                prev_test_reports.append(int(file_name.split('-')[-1].split('.')[0]))

        prev_test_reports.sort()
        test_report = prev_test_reports[-1] + 1 if prev_test_reports else 1
    else:
        test_report = int(test_report)

    # Output file name, with the path
    output_file_name_path = output_file_path + '/' + name_start + f'{test_report:03d}' + '.txt'

    with open(output_file_name_path, 'w', encoding='UTF8', newline='') as file:
        writer = csv.writer(file, delimiter='|')

        # write the header
        writer.writerow(output_file_header)

        # write the general info line, if multiple descriptions/versions are found all are written to the output file
        version = get_version(cmd_steps, logger)
        description = get_general_run_info_info(general_run_infos, 'descr', logger)
        writer.writerow([test_name, description, 'Test Spec. Version: ' + version, 'Test Rep. Version: ' + f'{test_report:03d}'])

        # write date line, first Date (Specification Date) is the last time the json file was changed or None if no json file was given
        # second Date (Execution Date), Is the execution Date of the first step
        date_format = '%Y-%m-%d'
        specification_date = datetime.datetime.strftime(datetime.datetime.fromtimestamp(os.stat(json_file_path).st_mtime), date_format) if os.path.isfile(json_file_path) else ''  # When was the last time the json file was changed?
        time_execution = datetime.datetime.strftime(cmd_steps[0]['exec_date'], date_format)
        writer.writerow(['Date', '', specification_date, time_execution])

        # write Precon line (Precon Descritpion)
        precon_descr = get_general_run_info_info(precon_info, 'precon_descr', logger)
        writer.writerow(['Precon.', precon_descr, '', ''])

        # write the general comment line, the Test Comment is only shown if it exists
        general_comment = get_general_run_info_info(general_run_infos, 'comment', logger)
        if general_comment:
            writer.writerow(['Comment', general_comment, '', ''])

        # write step line with Step Description, VRC Step Description and Result
        for step in cmd_steps:
            for vrc_step in vrc_steps:
                if step['step_id'] == vrc_step['step_id']:
                    test_result = 'VERIFIED' if vrc_step['result'] else 'FAILED'
                    # Secondary Counter is not shown if it is 0
                    step_number_primary, step_number_secondary = step['step'].split('_')
                    step_number_shown = step_number_primary if int(
                        step_number_secondary) == 0 else '{}.{}'.format(step_number_primary,
                                                                        step_number_secondary)
                    step_desc = 'Step ' + str(step_number_shown)
                    writer.writerow([step_desc, step['descr'], vrc_step['vrc_descr'], test_result])
                    if step['comment']:
                        writer.writerow(['Comment', step['comment'], '', ''])

        # write Postcon line (Post Con Description)
        postcon_descr = get_general_run_info_info(postcon_info, 'postcon_descr', logger)
        writer.writerow(['Postcon.', postcon_descr, '', ''])


def get_general_run_info_info(general_run_infos, info_keyword, logger):
    """
    Get one information from the given general_run_infos (Typically: Description, General Commen, Pre/Post Conditions)
    :param list of dicts general_run_infos: all the general run information that were found
    :param str info_keyword: Which information should be extracted from the general run infos
    :return str description: A string that contains all found informations
    """
    info = ''
    for count, run_info in enumerate(general_run_infos):
        if count == 0:
            info = run_info[info_keyword]
        else:
            info += ' / ' + run_info[info_keyword]
            if logger:
                logger.warning('More than one {} was found in the command log File'.format(info_keyword))
            else:
                print('More than one {} was found in the command log File'.format(info_keyword))

    return info


def get_version(steps, logger):
    """
    Get a string of the different version that could be found
    :param list of dicts steps: all the steps from the log file
    :return str version_final: A string that contains all found versions
    """
    version_list = []
    version_final = ''
    for step in steps:
        if step['version'] not in version_list:
            version_list.append(step['version'])
    for count, version in enumerate(version_list):
        if count == 0:
            version_final = version
        else:
            version_final += ' / ' + version
            if logger:
                logger.warning('More than one Version was found in the command log File')
            else:
                print('More than one Version was found in the command log File')
    return version_final

def show_basic_results(test_name, log_file_path=None):
    """
    Analyses the command and verification log file and prints a basic overview of the results
    :param str test_name: the name of the test and of its log files
    :param str log_file_path: Path to the log files, None if basic one should be used
    """
    if log_file_path:
        cmd_log_file = log_file_path + test_name + cmd_log_file_end
        vrc_log_file = log_file_path + test_name + vrc_log_file_end
    else:
        cmd_log_file = basic_log_file_path + test_name + cmd_log_file_end
        vrc_log_file = basic_log_file_path + test_name + vrc_log_file_end

    print('\n--------------------------------------------------')
    print('Analysis of the Command log file:')
    # find and parse all TC in the example_log_file
    tcs = analyse_command_log.get_sent_tcs(cmd_log_file)

    # find all steps in the example_log_file
    steps = analyse_command_log.get_steps_and_commands(cmd_log_file)
    print('\nCommand steps ({} total):'.format(len(steps)))
    for item in steps:
        print('Step {}: start: {}; end: {}'.format(item['step'], item['start_timestamp'], item['end_timestamp']))
    print('\n--------------------------------------------------')

    print('Analysis of the Verification log file:')
    # find all steps in the given log_file
    vrc_steps = analyse_verification_log.get_verification_steps(vrc_log_file)
    print('\nVerification steps ({} total):'.format(len(vrc_steps)))
    for item in vrc_steps:
        print('Verification Step {}: start: {}; end: {}; result: {}'.format(item['step'], item['start_timestamp'],
                                                                            item['end_timestamp'], item['result']))
    print('\n--------------------------------------------------')
    return

if __name__ == '__main__':
    #save_result_to_file(test_name, run_id=run_id)
    show_basic_results(test_name)
