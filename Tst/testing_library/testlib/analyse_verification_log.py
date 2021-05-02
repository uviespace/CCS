#!/usr/bin/env python3
"""
Analyzing the log file of the Verification Script. Get the information which Verifications were done and if they were
successful.
"""
from . import report
from . import testing_logger


def get_verification_steps(filename):
    """
    Get information of verification steps which could be found in the log file
    :param filename: path to the log file
    :return: list of all steps as a dictionaries of step number, start timestamp (CUC) of the verification,
             end timestamp (CUC) of the verification and the result of the verification for this step
    :rtype: list of dict
    """
    vrc_start = []
    vrc_end = []
    with open(filename, 'r') as fileobject:
        for line in fileobject:
            if report.key_word_found(line, report.vrc_step_keyword):
                new_dict = report.parse_step_from_json_string(line, report.vrc_step_keyword)
                new_dict['exec_date'] = testing_logger.extract_date(line)
                vrc_start.append(new_dict)
            if report.key_word_found(line, report.vrc_step_keyword_done):
                vrc_end.append(report.parse_step_from_json_string(line, report.vrc_step_keyword_done))
        fileobject.close()

    # print('\nfound {} steps:'.format(len(vrc_start)))
    # for item in vrc_start:
    #     print('Verification start for Step {} @ {}'.format(item['step'], item['timestamp']))
    #
    # for item in vrc_start:
    #     print('Verification end for Step {} @ {}'.format(item['step'], item['timestamp']))

    vrc_steps = []
    for item in vrc_start:
        new_vrc_step = {}
        new_vrc_step['step'] = item['step']
        new_vrc_step['start_timestamp'] = item['timestamp']
        new_vrc_step['exec_date'] = item['exec_date']
        new_vrc_step['version'] = item['version']
        for element in vrc_end:
            if element['step'] == item['step']:
                new_vrc_step['end_timestamp'] = element['timestamp']
                new_vrc_step['result'] = element['result']
        vrc_steps.append(new_vrc_step)

    print('\nVerification steps ({} total):'.format(len(vrc_start)))
    for item in vrc_steps:
        print('Verification Step {}: start: {}; end: {}; result: {}'.format(item['step'], item['start_timestamp'], item['end_timestamp'], item['result']))

    return vrc_steps


if __name__ == '__main__':
    example_log_file = '../logs_test_runs/simple_example_verification.log'

    # find all steps in the example_log_file
    steps = get_verification_steps(example_log_file)