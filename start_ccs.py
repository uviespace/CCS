#!/usr/bin/python3
import sys
import os
import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
sys.path.append(confignator.get_option('paths', 'tst'))
import ccs_function_lib as cfl


if __name__ == '__main__':
    files_to_open = ()
        # os.path.join(confignator.get_option('paths', 'tst'), 'prep_test_env.py'),
        # os.path.join(confignator.get_option('paths', 'obsw'), 'send_TC.py')

    cfl.start_editor(False, *files_to_open)
