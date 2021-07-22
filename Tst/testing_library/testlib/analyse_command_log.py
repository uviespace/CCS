#!/usr/bin/env python3
"""
Analyzing the log file of the Command Script. Get the information which Steps were done and which TC were sent.
"""
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()
from testlib import report
from testlib import testing_logger
from testlib import tcid


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
    Get all steps which could be found in the log file, deprecated version (does not use step id or run id, use
    get_steps_and_commands function below)
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

def get_test_description(filename):
    """
    Returns the Test Description, If two are identical only one of them is returned
    :param filename: path to the log file
    :return: list of test descriptions
    :rtype: list of str
    """
    if not filename:
        return ''
    descr_list = []
    with open(filename, 'r') as fileobject:
        for line in fileobject:
            if report.key_word_found(line, report.cmd_test_start_keyword):
                general_step_info = report.parse_step_from_json_string(line, report.cmd_test_start_keyword)
                if general_step_info['descr'] not in descr_list:
                    descr_list.append(general_step_info['descr'])

    for count, descr in enumerate(descr_list):
        if count == 0:
            description = descr
        else:
            description += ' / ' + descr
            print('More than one Description was found in the command log File')
    return description

def get_steps_and_commands(filename):
    """
    Get all steps which could be found in the log file and identifiy step start/end by step_id
    :param filename: path to the log file
    :return: all found steps
    :rtype: list of dict
    """
    steps = []
    steps_start = []
    steps_end = []

    def new_step_template_start():
        return {'step': None, 'version': '', 'tcs': [], 'date': ''}

    def new_step_template_end():
        return {'step': None, 'timestamp': '', 'step_id': ''}

    new_step = new_step_template_start()
    run_count = 1

    with open(filename, 'r') as fileobject:
        for line in fileobject:
            #if report.key_word_found(line, report.cmd_test_start_keyword):
                # Get general infos about the whole test, append to every step of this run
                #general_step_info = report.parse_step_from_json_string(line, report.cmd_test_start_keyword)
                #general_step_info['run_count'] = str(run_count)
                #run_count += 1
            if report.key_word_found(line, report.cmd_step_keyword):
                if new_step['step'] is not None:
                    steps_start.append(new_step)
                new_step = new_step_template_start()
                # get date of the step execution
                new_step['exec_date'] = testing_logger.extract_date(line)
                # get the information about the step
                step_start_info = report.parse_step_from_json_string(line, report.cmd_step_keyword)
                if step_start_info is not None:
                    new_step['step'] = step_start_info['step']
                    new_step['start_timestamp'] = step_start_info['timestamp']
                    new_step['version'] = step_start_info['version']
                    new_step['descr'] = step_start_info['descr']
                    new_step['run_id'] = step_start_info['run_id']
                    new_step['step_id'] = step_start_info['step_id']
                    new_step['comment'] = step_start_info['comment']
                #try:
                #    new_step['general_run_info'] = general_step_info
                #except:
                #    new_step['general_run_info'] = None
            if tcid.key_word_found(line):
                new_tc_id = tcid.TcId()
                new_tc_id.parse_tc_id_from_json_string(line=line)
                new_step['tcs'].append(new_tc_id)
            if report.key_word_found(line, report.cmd_step_exception_keyword):
                new_step['exception'] = True
            if report.key_word_found(line, report.cmd_step_keyword_done):
                step_end_info = report.parse_step_from_json_string(line, report.cmd_step_keyword_done)
                if step_end_info is not None:
                    new_step_end = new_step_template_end()
                    new_step_end['step'] = step_end_info['step']
                    new_step_end['timestamp'] = step_end_info['timestamp']
                    new_step_end['step_id'] = step_end_info['step_id']
                    steps_end.append(new_step_end)
                    #if new_step['step'] == step_end_info['step']:
                    #    new_step['end_timestamp'] = step_end_info['timestamp']
                    #else:
                    #    print('get_steps_and_commands: the step number in the step-end string is different than the'
                    #          'step number of the last step-start string.')
        if new_step['step'] is not None:
            steps_start.append(new_step)
        fileobject.close()

    if len(steps_end) > len(steps_start):
        print('More steps ended than started, something went wrong')

    for start_info in steps_start:
        for end_info in steps_end:
            if start_info['step_id'] == end_info['step_id']:
                start_info['end_timestamp'] = end_info['timestamp']

    return steps_start

def get_general_run_info(filename, run_id=None):
    """
    Get all lines with general run information, those are logged if whole test is executed, returns all found lines, or
    only 1 if run_id is specified
    :param filename: path to the log file
    :return: all found general step infomations
    :rtype: list of dict
    """
    general_infos = []
    precon_infos = []
    postcon_infos = []
    with open(filename, 'r') as fileobject:
        for line in fileobject:
            if report.key_word_found(line, report.cmd_test_start_keyword):
                general_run_info = report.parse_step_from_json_string(line, report.cmd_test_start_keyword)
                if not run_id:
                    general_infos.append(general_run_info)
                elif general_run_info['run_id'] == run_id:
                    general_infos.append(general_run_info)

            elif report.key_word_found(line, report.cmd_precon_keyword):
                precon = report.parse_step_from_json_string(line, report.cmd_precon_keyword)
                if not run_id:
                    precon_infos.append(precon)
                elif precon['run_id'] == run_id:
                    precon_infos.append(precon)

            elif report.key_word_found(line, report.cmd_postcon_keyword):
                postcon = report.parse_step_from_json_string(line, report.cmd_postcon_keyword)
                if not run_id:
                    postcon_infos.append(postcon)
                elif postcon['run_id'] == run_id:
                    postcon_infos.append(postcon)

    return general_infos, precon_infos, postcon_infos

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
