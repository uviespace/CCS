#!/usr/bin/env python3
"""
Gives a pretty print overview of the outcome of a test run. For this the log files of the executed Command and Verification scripts are used.
"""
from . import analyse_verification_log
from . import analyse_command_log

if __name__ == '__main__':
    example_cmd_log_file = '../logs_test_runs/simple_example_command.log'
    example_ver_log_file = '../logs_test_runs/simple_example_verification.log'

    print('\n--------------------------------------------------')
    print('Analysis of the Command log file:')
    # find and parse all TC in the example_log_file
    tcs = analyse_command_log.get_sent_tcs(example_cmd_log_file)

    # find all steps in the example_log_file
    steps = analyse_command_log.get_steps(example_cmd_log_file)

    print('\n--------------------------------------------------')
    print('Analysis of the Verification log file:')
    # find all steps in the example_log_file
    vrc_steps = analyse_verification_log.get_verification_steps(example_ver_log_file)
    print('\n--------------------------------------------------')
