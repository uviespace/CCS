#!/usr/bin/env python3
"""
Analyzing the log file of the Command Script. Get the information which Steps were done and which TC were sent.
"""
from . import report
from . import testing_logger
from . import tcid


def get_sent_tcs(filename):
    """
    Get all sent TCs which could be found in the log file
    :param filename: path to the log file
    :return: list of all sent TC as telecommand identifier instance (class TcId)
    :rtype: list of TcId instances
    """
    sent_tcs = []
    with open(filename, 'r') as fileobject:
        for line in fileobject:
            if tcid.key_word_found(line):
                new_tc_id = tcid.TcId()
                new_tc_id.parse_tc_id_from_json_string(line=line)
                sent_tcs.append(new_tc_id)
        fileobject.close()

    print('\nfound {} TCs:'.format(len(sent_tcs)))
    for item in sent_tcs:
        print(
            'TC({},{}) with SSC {} to APID {} @ {}'.format(item.st, item.sst, item.ssc, item.apid, item.timestamp))

    return sent_tcs


def get_steps(filename):
    """
    Get all steps which could be found in the log file
    :param filename: path to the log file
    :return: list of all steps as a dictionaries of step number and step starting timestamp (CUC)
    :rtype: list of dict
    """
    steps_start = []
    steps_end = []
    with open(filename, 'r') as fileobject:
        for line in fileobject:
            if report.key_word_found(line, report.cmd_step_keyword):
                steps_start.append(report.parse_step_from_json_string(line, report.cmd_step_keyword))
            if report.key_word_found(line, report.cmd_step_keyword_done):
                steps_end.append(report.parse_step_from_json_string(line, report.cmd_step_keyword_done))
        fileobject.close()

    # print('\nfound {} steps:'.format(len(steps_start)))
    # for item in steps_start:
    #     print('Step {} @ {}'.format(item['step'], item['timestamp']))
    #
    # for item in steps_end:
    #     print('Step {} done @ {}'.format(item['step'], item['timestamp']))

    steps = []
    for item in steps_start:
        new_vrc_step = {}
        new_vrc_step['step'] = item['step']
        new_vrc_step['start_timestamp'] = item['timestamp']
        for element in steps_end:
            if element['step'] == item['step']:
                new_vrc_step['end_timestamp'] = element['timestamp']
        steps.append(new_vrc_step)

    print('\nCommand steps ({} total):'.format(len(steps)))
    for item in steps:
        print('Step {}: start: {}; end: {}'.format(item['step'], item['start_timestamp'], item['end_timestamp']))

    return steps


def get_steps_and_commands(filename):
    """
    ???
    :param filename: path to the log file
    :return:
    :rtype: list of dict
    """
    steps = []

    def new_step_template():
        return {'step': None, 'version': '', 'tcs': [], 'date': ''}

    new_step = new_step_template()

    with open(filename, 'r') as fileobject:
        for line in fileobject:
            if report.key_word_found(line, report.cmd_step_keyword):
                if new_step['step'] is not None:
                    steps.append(new_step)
                new_step = new_step_template()
                # get date of the step execution
                new_step['exec_date'] = testing_logger.extract_date(line)
                # get the information about the step
                step_start_info = report.parse_step_from_json_string(line, report.cmd_step_keyword)
                if step_start_info is not None:
                    new_step['step'] = step_start_info['step']
                    new_step['start_timestamp'] = step_start_info['timestamp']
                    new_step['version'] = step_start_info['version']
            if tcid.key_word_found(line):
                new_tc_id = tcid.TcId()
                new_tc_id.parse_tc_id_from_json_string(line=line)
                new_step['tcs'].append(new_tc_id)
            if report.key_word_found(line, report.cmd_step_exception_keyword):
                new_step['exception'] = True
            if report.key_word_found(line, report.cmd_step_keyword_done):
                step_end_info = report.parse_step_from_json_string(line, report.cmd_step_keyword_done)
                if step_end_info is not None:
                    if new_step['step'] == step_end_info['step']:
                        new_step['end_timestamp'] = step_end_info['timestamp']
                    else:
                        print('get_steps_and_commands: the step number in the step-end string is different than the'
                              'step number of the last step-start string.')
        if new_step['step'] is not None:
            steps.append(new_step)
        fileobject.close()

    return steps


if __name__ == '__main__':
    example_log_file = '../logs_test_runs/simple_example_command.log'

    # show how a TcId instance is decoded to a JSON string
    st = 3
    sst = 6
    ssc = 24
    apid = 332
    t = 1543837991.0306091
    telecommand_identifier = tcid.TcId(st=st, sst=sst, ssc=ssc, apid=apid, timestamp=t)
    print('\n{}'.format(telecommand_identifier.json_dump_for_logging()))

    # find and parse all TC in the example_log_file
    tcs = get_sent_tcs(example_log_file)

    # find all steps in the example_log_file
    steps = get_steps(example_log_file)

    get_steps_and_commands(example_log_file)
