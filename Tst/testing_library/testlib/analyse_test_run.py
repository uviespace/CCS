#!/usr/bin/env python3
"""
Gives a pretty print overview of the outcome of a test run. For this the log files of the executed Command and Verification scripts are used.
"""
import confignator
import csv
import datetime
import os
from os import listdir
from os.path import isfile, join

import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()

from testlib import analyse_verification_log
from testlib import analyse_command_log

test_name = 'test3'

cmd_log_file_end = '_command.log'
vrc_log_file_end = '_verification.log'
basic_log_file_path = confignator.get_option('tst-logging', 'test_run')
basic_output_file_path = confignator.get_option('tst-logging', 'test_run')  # TODO: Set basic output path (Dominik)
output_file_header = ['Item', 'Description', 'Verification', 'TestResult']

def result_as_csv(test_name, log_file_path=None, output_file_path=None):
    """
    Analyses the command and verification log file and creates a csv output table
    :param str test_name: the name of the test and of its log files
    :param str log_file_path: Path to the log files, None if basic one should be used
    """
    if not log_file_path:
        log_file_path = basic_log_file_path
    if not output_file_path:
        output_file_path = basic_output_file_path

    cmd_log_file = log_file_path + test_name + cmd_log_file_end
    vrc_log_file = log_file_path + test_name + vrc_log_file_end

    cmd_steps = analyse_command_log.get_steps_and_commands(cmd_log_file)
    vrc_steps = analyse_verification_log.get_verification_steps(vrc_log_file)

    name_start = 'IASW-{}-TS-{}-TR-'.format(test_name, cmd_steps[0]['version'])  # TODO: Check which name should be used, version always same in log file?
    file_versions = []

    for file_name in listdir(output_file_path):
        if file_name.startswith(name_start):
            file_versions.append(int(file_name.split('-')[-1].split('.')[0]))

    file_versions.sort()
    file_count = file_versions[-1] + 1 if file_versions else 1
    output_file_name_path = output_file_path + name_start + f'{file_count:03d}' + '.txt'

    with open(output_file_name_path, 'w', encoding='UTF8', newline='') as file:
        writer = csv.writer(file, delimiter='|')

        # write the header
        writer.writerow(output_file_header)

        # write the general info line
        writer.writerow([test_name, 'Test Description', 'Test Spec. Version: ' + cmd_steps[0]['version'], 'Test Rep. Version: ' + f'{file_count:03d}'])  # TODO: version always same in log file?

        # write date line
        date_format = '%Y-%m-%d'
        exec_date = datetime.datetime.strftime(cmd_steps[0]['exec_date'], date_format)
        time_now = datetime.datetime.strftime(datetime.datetime.now(), date_format)
        writer.writerow(['Date', '', exec_date, time_now])  # TODO: Make sure which dates should be shown, ok to take time from first step?

        # write Precon line
        writer.writerow(['Precon.', 'This has still to be solved', '', ''])  # TODO: What should be shown of the Precon

        # write comment line
        writer.writerow(['Comment', 'This is NOT a comment, still working on it', '', ''])  # TODO: Where is the comment given?

        # write comment line
        for step in cmd_steps:
            for vrc_step in vrc_steps:
                if step['step_id'] == vrc_step['step_id']:
                    test_result = 'VERIFIED' if vrc_step['result'] else 'FAILED'
                    writer.writerow(['Step ' + step['step'][:-2], step['descr'], 'Probably some VRC description', test_result])  # TODO: Third coloumn is what?

        # write Postcon line
        writer.writerow(['Postcon.', 'This has still to be solved', '', ''])  # TODO: What should be shown of the Postcon


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
    result_as_csv(test_name)
    #show_basic_results(test_name)
