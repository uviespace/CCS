#!/usr/bin/env python3
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()
import tst

if __name__ == '__main__':
    tst.run()
