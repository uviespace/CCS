"""
Quick'n'Dirty script to load the steps of the CHEOPS IASW test specification into the DB
"""
import inspect
import os
import sys
import db_schema
from db_schema import CodeBlock

IASW_test_specs_folder = os.path.realpath('/home/swiii/IFSW/acceptance_tests/v0.6/IASW/')

sys.path.append(os.path.realpath('/home/swiii/IFSW/acceptance_tests/v0.6/'))
sys.path.append(IASW_test_specs_folder)


def get_step_functions(test_class):
    # get all step functions
    step_funcs = []
    counter = 1
    while counter < 1000:
        try:
            step_func_name = 'step_{}'.format(counter)
            step_func = test_class.__getattribute__(test_class, step_func_name)
            lines = inspect.getsource(step_func)
            # remove the first line and the indent
            newrow = '\n        '
            func_body = lines[lines.find(newrow) + len(newrow):]
            outdented_func_body = func_body.replace(newrow, '\n')
            step_funcs.append(outdented_func_body)
            counter += 1
        except:
            break
    return step_funcs


def add_step(descripition, command_code):
    session.add(CodeBlock(code_type="step",
                          description=descripition,
                          command_code=command_code))
    session.commit()


if __name__ == '__main__':
    with db_schema.session_scope() as session:
        # get all files within the folder
        files = os.listdir(IASW_test_specs_folder)
        for index, entry in enumerate(files):
            # strip the file extention from the list entries
            files[index] = entry.rstrip('.py')

        # remove the __pycache__ file
        files.pop(files.index('__pycache__'))

        for entry in files:
            # import a test spec, read it and write the steps into the database
            exec('import {}'.format(entry))
            # get the class name
            cn1 = entry.rstrip('_DB')
            cn2 = cn1.replace('_', '')
            class_name = 'Test' + cn2
            exec('test_class = {}.{}'.format(entry, class_name))
            exec('test_instance = {}.{}()'.format(entry, class_name))
            test_name = test_instance.name
            test_description = test_instance.description
            test_comment = test_instance.comment

            step_functions = get_step_functions(test_class=test_class)
            for entry in step_functions:
                step_param_start = entry.find('param = {')
                step_param_end = entry.find('report.write_log_step_header')
                step_param_string = entry[step_param_start:step_param_end]
                exec(step_param_string)
                step_description = param['msg']

                add_step(descripition=step_description, command_code=entry)
