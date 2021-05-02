#!/usr/bin/env python3
""" 
This script should prepare the environment for running tests automatically and should be the entry point.
    Following steps are done:
    * configuration file egse.cfg is read
    * a instance of the poolmanager is created
    * a instance of the CCScom is created
    * a mode is selected:
        ** 'ADS'
        ** 'CrObc' run it with simulators
        ** 'UVIE'
    * a set of tests are executed in a separate thread
"""
import logging
import os
import subprocess
import sys
import threading
import time

# Add the path of the integration test scripts, thus Python can find the modules.
print(os.getcwd())
if os.path.isdir(os.path.realpath('../../Tst/')):
    sys.path.append(os.path.realpath('../../Tst/'))
else:
    logging.error('Failed to add to path: "{}"'.format(path_to_add_1))
path_to_add_2 = os.path.realpath('../Ccs/esa/')
if os.path.isdir(path_to_add_2):
    sys.path.append(path_to_add_2)
else:
    logging.error('Failed to add to path: "{}"'.format(path_to_add_2))

import packets
import poolview_sql
import pus_datapool
import start_pool_viewer

from testlib import tools
from testlib import sim
from testlib import config_logging


loglevel = 'DEBUG'  # CRITICAL, ERROR, WARNING, INFO, DEBUG

# load the predefined logging configuration
config_logging.setup_logging(log_file_name='summary', level=loglevel)
# create logger
logger = logging.getLogger('run_tests')


def run_test_set(ccs, pool_name, test_set=None):
    lalinea = '--------------------------------'
    if test_set is not None:
        try:
            # execute the tests which are specified in test_set
            result = []
            exceptions = []
            logger.info('Executing a set of {} tests.'.format(len(test_set)))
            for i in range(len(test_set)):
                try:
                    logger.info('    Running test {}.'.format(test_set[i].name))
                    result.append(test_set[i].run(ccs=ccs, pool_name=pool_name, loglevel=loglevel, check_integrity=False))
                except Exception:
                    exceptions.append((test_set[i].name, sys.exc_info()))
                    logger.error('        An Exception occurred while running test {}.'.format(test_set[i].name))

            # write summary of the integration tests if there was run more than one test
            logger.info('================================')
            logger.info('Summary for integration test runs')
            logger.info(lalinea)
            for test in result:
                if test.name == '?':
                    test.name = test.id
                logger.info('{}'.format(test.name))
                successful_steps = 0
                if len(test.step_results) == 0:
                    if test.precond_ok is False:
                        logger.info('Precondition not fulfilled!')
                    logger.info('No steps were ran successfully.')
                for item in test.step_results:
                    if item['result'] is not True:
                        if 'exception' in item:
                            logger.info('\t{} step {} FAILED because of an EXCEPTION!'.format(test.id, item['step']))
                        else:
                            logger.info('\t{} step {} FAILED!'.format(test.id, item['step']))
                    else:
                        successful_steps += 1
                        logger.info('\t{} step {} OK'.format(test.id, item['step']))
                if successful_steps == test.number_of_steps:
                    logger.info('{} SUCCESS: {}/{} steps passed'.format(test.name, successful_steps, test.number_of_steps))
                else:
                    logger.info('{} FAILED: {}/{} steps passed'.format(test.name, successful_steps, test.number_of_steps))
                logger.info(lalinea)

            # give out every exception which occoured in a test step while executing it
            logger.info('================================')
            logger.info('Exceptions which occurred on test step level:')
            has_exc = False
            for test in result:
                if len(test.exceptions) > 0:
                    has_exc = True
                    for exce in test.exceptions:
                        logger.error('Exception in {}'.format(test.id), exc_info=exce)
            if has_exc is False:
                logger.info('No exceptions')

            # give out every exception which occoured while running a test
            logger.info('================================')
            logger.info('Exceptions which occurred on test execution:')
            if len(exceptions) > 0:
                for excep in exceptions:
                    logger.error('exception in {}'.format(excep[0]), exc_info=excep[1])
            else:
                logger.info('No exceptions')
            logger.info('================================')

        except AttributeError:
            logger.error('run_test_set: Attributes of the test class do not exist.')
            logger.exception(AttributeError)


def start_pv(cfg, ccs, pool_name, as_thread):
    poolviewer = None
    if as_thread is True:
        poolviewer = threading.Thread(target=start_pool_viewer.start_it, args=(cfg, ccs, pool_name))
        poolviewer.setDaemon(True)
        poolviewer.start()
        time.sleep(1)
    else:
        poolviewer = poolview_sql.TMPoolView(cfg)
        poolviewer.set_ccs(ccs)
        poolviewer.set_pool(pool_name)
        poolviewer.show_all()
    return poolviewer

#! CCS.BREAKPOINT
 ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    # if the script is ran from the CCS-Editor the behavior is different
    if 'shared' in globals():  # this seems to be the only way to determine if in CSS or not, this line is not good
        script_ran_via_ccs = True
    else:
        script_ran_via_ccs = False
    logger.info('run_tests.py is executed from within CCS Editor: {}'.format(script_ran_via_ccs))

    # crucial parameters
    pool_name = 'LIVE'
    egse = 'CrObc'
    start_sims = True
    start_poolviewer = True
    if script_ran_via_ccs is True:
        pv_as_thread = False
    else:
        pv_as_thread = True

    obc = None
    cria = None

    # delete the entries of table 'tm' in the database
    # tm_db.truncate_tm_table(ccs=ccs)
    ##! CCS.BREAKPOINT
    # load the configuration file
    if 'cfg' not in globals():
        cfg = tools.read_config_file()
    ##! CCS.BREAKPOINT
    # create a instance of  the PUSDatapoolManager
    if 'poolmanager' not in globals():
        logger.debug('Creating a instance of PUSDatapoolManager')
        poolmanager = pus_datapool.PUSDatapoolManager(cfg=cfg)
    ##! CCS.BREAKPOINT
    # create a instance of CCScom
    if 'ccs' not in globals():
       logger.debug('Creating a instance of CCScom')
       ccs = packets.CCScom(cfg=cfg, poolmgr=poolmanager)
    ##! CCS.BREAKPOINT
    # ADS PS
    if egse == 'ADS':
        # connect
        poolmanager.connect(pool_name=pool_name, host='10.0.0.1', port=60003)
        poolmanager.connect_tc(pool_name=pool_name, host='10.0.0.1', port=60001, drop_rx=True)
        # start the pool-viewer
        if start_poolviewer is True:
            poolviewer = start_pv(cfg=cfg, ccs=ccs, pool_name=pool_name, as_thread=pv_as_thread)
        time.sleep(1)
        ccs.CnCsend(cmd='TRANSFER remote', pool_name=pool_name)
        
    # CrObc
    if egse == 'CrObc':
        if start_sims is True:
            # start the simulators if they are not running already
            obc_already_running = sim.obc_runs()
            if not obc_already_running:
                print(os.getcwd())
                obc = sim.start_obc()
            else:
                logger.info('CrObc simulator seem to run already.')
            ia_already_running = sim.ia_runs()
            if not ia_already_running:
                cria = sim.start_ia()
            else:
                logger.info('CrIa simulator seem to run already.')
            time.sleep(1)
        # connect
        try:
            logger.info('connecting to 127.0.0.1 ...')
            poolmanager.connect(pool_name=pool_name, host='127.0.0.1', port=5570)
            poolmanager.connect_tc(pool_name=pool_name, host='127.0.0.1', port=5571)
        except ConnectionRefusedError:  # try again in a few seconds
            logger.error('Connection was refused')
            logger.exception(ConnectionRefusedError)
            logger.error('Retrying in 3 seconds...')
            time.sleep(3)
            poolmanager.connect(pool_name=pool_name, host='127.0.0.1', port=5570)
            poolmanager.connect_tc(pool_name=pool_name, host='127.0.0.1', port=5571)
        time.sleep(3)
        # start the pool-viewer
        if start_poolviewer is True:
            logger.info('starting the Pool-Viewer\n')
            poolviewer = start_pv(cfg=cfg, ccs=ccs, pool_name=pool_name, as_thread=pv_as_thread)
            
    # UVIE PS
    if egse == 'UVIE':
        # connect
        poolmanager.connect(pool_name=pool_name, host='127.0.0.1', port=1234)
        poolmanager.connect_tc(pool_name=pool_name, host='127.0.0.1', port=1234)
        # start the pool-viewer
        if start_poolviewer is True:
            poolviewer = start_pv(cfg=cfg, ccs=ccs, pool_name=pool_name, as_thread=pv_as_thread)

    # add the information which egse case is used, in order to distinguish if the SEM simulator process is started
    ccs.egse = egse

    #! CCS.BREAKPOINT

    test_set = []

    if len(test_set) > 0:
        # run the tests as a thread, thus the Pool-Viewer is not locked
        tests = threading.Thread(target=run_test_set, name='Thread-RunTests',
                                 kwargs={'ccs': ccs, 'pool_name': pool_name, 'test_set': test_set})
        tests.daemon = True
        tests.start()
        # if the script is not ran within the CCS-Editor wait for the thread to terminate
        if not script_ran_via_ccs:
            tests.join()

        # shut off what the script turned on, if the script is not ran within the CCS-Editor
        if not script_ran_via_ccs:
            if start_sims is True:
                # terminate the OBC, CrIa
                if isinstance(obc, subprocess.Popen):
                    sim.stop_obc(obc)
                if isinstance(cria, subprocess.Popen):
                    sim.stop_ia(cria)
            if start_poolviewer is True:
                # wait for the user to press a key (then the program exits and the Pool-Viewer is closed)
                input("Done.")
