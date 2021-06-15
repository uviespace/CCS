#!/usr/bin/env python3
"""
This script should prepare the environment for running tests automatically and should be the entry point.
    Following steps are done:
    * the OnBoard computer CrPlm simulator is started as a own process
    * the Instrument computer CrIa simulator is started as a own process
    * the PoolManager is started as a own process
    * the PoolViewer is started as a own process
"""
import logging
import os
import time
import sys
import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
sys.path.append(confignator.get_option('paths', 'tst'))
import ccs_function_lib as cfl
import toolbox
import start_stop_simulators
import connect_apps

log_file_path = confignator.get_option(section='logging', option='log-dir')
log_file = os.path.join(log_file_path, 'prep_test_env.log')

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)
file_hdlr = toolbox.create_file_handler(file=log_file)
logger.addHandler(hdlr=file_hdlr)

pool_name = 'new_tmtc_pool'

def run(pool_name):
    logger.info('1) ------------------- Start the simulators -------------------')
    start_stop_simulators.start_crplm(logger=logger)
    start_stop_simulators.start_cria(logger=logger)

    time.sleep(1)

    logger.info('2) ------------------- Start the PoolManager -------------------')
    if not cfl.is_open('poolmanager'):
        cfl.start_pmgr()
    else:
        time.sleep(2)
    pm = connect_apps.connect_to_app('poolmanager', logger=logger)
    logger.info('4) ------------------- Connect the Poolmanager to OBC & TMpool database-------------------')
    if pm is not False:
        time.sleep(2)
        pm.Functions('connect', pool_name, '127.0.0.1', 5570, True)
        pm.Functions('connect_tc', pool_name, '127.0.0.1', 5571, True)
    else:
        logger.critical('FAILED TO CONNECT TO POOLMANAGER!')

    if pm is not False:
        logger.info('3) ------------------- Start the PoolViewer -------------------')
        if not cfl.is_open('poolviewer'):
            cfl.start_pv()
        else:
            time.sleep(2)
        pv = connect_apps.connect_to_app('poolviewer', logger=logger)

        if pv is not False:
            pv.Functions('set_pool', pool_name)
        else:
            logger.critical('FAILED TO CONNECT TO POOLVIEWER!')

        if pm is not False and pv is not False:
            logger.info('--------------------------READY!--------------------------\n\n\n')
        else:
            logger.info('-------------------------- STARTING UP FAILED --------------------------------\n\n\n')
    else:
        logger.info('-------------------------- STARTING UP FAILED --------------------------------\n\n\n')


if __name__ == '__main__':
    run(pool_name=pool_name)
