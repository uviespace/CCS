#!/usr/bin/python
"""
How to abort a step?
If steps are executed as threads: How to do the logging?
If parallel tests (as GTK application) are run, how to do the logging?
"""
import logging
import sys
import os
import time
import importlib
import threading
from testlib import tools
from testlib import report
from testlib import tm
from testlib import tc
from testlib import tcid
from testlib import precond
from testlib import testing_logger
from testlib import sim
path_to_add_1 = os.path.realpath('../../Tst/')
if os.path.isdir(path_to_add_1):
    sys.path.append(path_to_add_1)
else:
    logging.error('Failed to add to path: "{}"'.format(path_to_add_1))
path_to_add_2 = os.path.realpath('../../../../../IFSW/Ccs/esa/')
if os.path.isdir(path_to_add_2):
    sys.path.append(path_to_add_2)
else:
    logging.error('Failed to add to path: "{}"'.format(path_to_add_2))
import packets
import poolview_sql
import pus_datapool
import start_pool_viewer


# create logger
logger = logging.getLogger(__name__)
pool_name = 'LIVE'


class ExampleOne:
    def __init__(self, do_verification=False):
        self.id = 'Simple_Example'
        self.name = 'Simple Example'
        self.description = 'Test the basic functionality of TST'
        self.precondition = ''
        self.comment = ''
        self.number_of_steps = None
        self.successful_steps = 0
        self.step_results = []
        self.test_passed = None
        self.precond_ok = False
        self.integrity = True
        self.exceptions = []
        self.do_verification = do_verification

        # some tests are depended on other tests, thus information is stored on class level
        # insert class variables here

    @staticmethod
    def version():
        return '0.5.2'

    # STEP 1 --------------------------------------------------------------------------------------------------------
    def step_1(self, event, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '1',
            'msg': 'Use TC(3,6) to disable the generation of the IFSW_HK housekeeping report and verify that generation of this report stops',
            'comment': ''
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name,
                                  step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:

            i = 0
            while i < 20:
                if event.is_set():
                    print('Huzr')
                print('ExampleOne: step_1: count = {}'.format(i))
                time.sleep(3)
                i += 1


            # sending a TC(3,6) to disable IFSW_HK housekeeping
            # tc_dis = ccs.Tcsend_DB('DPU_IFSW_DIS_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)
            # tc_id = tcid.TcId(st=3, sst=6, apid=tc_dis[0], ssc=tc_dis[1], timestamp=tc_dis[2])

        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        return summary

    # STEP 2 --------------------------------------------------------------------------------------------------------
    def step_2(self, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '2',
            'msg': 'Enable the HK again and set its period to 4 seconds',
            'comment': ''
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name,
                                  step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:
            # send TC(3,5)
            ccs.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)
            # send TC(3,131)
            ccs.Tcsend_DB('DPU_IFSW_SET_HK_REP_FREQ', 1, 8 * 4, ack='0b1011', pool_name=pool_name)

        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        return summary

    # STEP 3 --------------------------------------------------------------------------------------------------------
    def step_3(self, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '3',
            'msg': 'This step should create an exception.',
            'comment': ''
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name,
                                  step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:
            raise Exception('This exception is intentionally.')
        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        return summary

    # EXECUTE ALL STEPS AUTOMATED --------------------------------------------------------------------------------------
    def run(self, ccs, pool_name, save_pool=True, loglevel='DEBUG', make_new_log_file=True):
        """
        Executes the steps of this test. Before running the steps the preconditions are checked.
        :param ccs: packets.CCScom
            Instance of the class packets.CCScom
        :param pool_name: str
            Name of the datapool for TM/TCs in the database
        :param save_pool: bool
            Set to False if the pool should not be saved e.g.: when this test is done at the end of another test.
        :param loglevel: str
            Defines the log level
        :param make_new_log_file: bool
            The logging writes to a file. If this variable is set to True, a new log-file is created.
        :return: instance of TestIASW66
            A instance of this test class
        """
        testing_logger.cmd_log_handler(__name__)

        # log the header of this test
        report.write_log_test_header(test=self, ccs=ccs, pool_name=pool_name)

        # preconditions of the test
        logger.info('Preconditions: {}'.format(self.precondition))
        # self.precond_ok = self.establish_preconditions(ccs=ccs, pool_name=pool_name)

        # if preconditions are met, execute the steps and note the results
        if True:
            # define the steps array
            steps = [
                self.step_1,
                self.step_2,
                self.step_3
            ]
            self.number_of_steps = len(steps)
            # execute all test steps
            for step in steps:
                try:
                    # run a single step
                    t_start = time.time()
                    res = step(ccs=ccs, pool_name=pool_name)
                    t_end = time.time()
                    logger.debug('runtime of step: {}s\n'.format(t_end - t_start))
                except Exception as error:
                    self.test_passed = False
                    res = report.StepSummary(step_number=step.__name__, result=False)
                    self.exceptions.append(sys.exc_info())
                    logger.critical('Exception in {}'.format(step))
                    logger.exception(error)
                    break
                finally:
                    # add the summary of the step to the result array
                    self.step_results.append(res)
        else:
            logger.error('Preconditions could not be established. Test steps were not executed!\n')

        # save the packet pool
        self.save_pool_in_file(ccs=ccs, pool_name=pool_name, save_pool=save_pool)

        # log the summary of this test
        self.successful_steps = report.write_log_test_footer(test=self)

        # this test has passed, if no Exception occoured, all steps were successful and the integrity is intact
        if self.test_passed is not False:
            if self.successful_steps == self.number_of_steps:
                self.test_passed = True

        return self

    def save_pool_in_file(self, ccs, pool_name, save_pool):
        if save_pool is True:
            pool_file = tools.get_path_for_testing_logs(ccs=ccs) + self.id + '.tmpool'
            ccs.savepool(filename=pool_file, pool_name=pool_name)


class ExampleTwo:
    def __init__(self, do_verification=False):
        self.id = 'Simple_Example'
        self.name = 'Simple Example'
        self.description = 'Test the basic functionality of TST'
        self.precondition = ''
        self.comment = ''
        self.number_of_steps = None
        self.successful_steps = 0
        self.step_results = []
        self.test_passed = None
        self.precond_ok = False
        self.integrity = True
        self.exceptions = []
        self.do_verification = do_verification

        # some tests are depended on other tests, thus information is stored on class level
        # insert class variables here

    @staticmethod
    def version():
        return '0.5.2'

    # STEP 1 --------------------------------------------------------------------------------------------------------
    def step_1(self, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '1',
            'msg': 'Use TC(3,6) to disable the generation of the IFSW_HK housekeeping report and verify that generation of this report stops',
            'comment': ''
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name,
                                  step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:
            # sending a TC(3,6) to disable IFSW_HK housekeeping
            tc_dis = ccs.Tcsend_DB('DPU_IFSW_DIS_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)
            tc_id = tcid.TcId(st=3, sst=6, apid=tc_dis[0], ssc=tc_dis[1], timestamp=tc_dis[2])

        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        return summary

    # STEP 2 --------------------------------------------------------------------------------------------------------
    def step_2(self, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '2',
            'msg': 'Enable the HK again and set its period to 4 seconds',
            'comment': ''
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name,
                                  step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:
            # send TC(3,5)
            ccs.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)
            # send TC(3,131)
            ccs.Tcsend_DB('DPU_IFSW_SET_HK_REP_FREQ', 1, 8 * 4, ack='0b1011', pool_name=pool_name)

        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        return summary

    # STEP 3 --------------------------------------------------------------------------------------------------------
    def step_3(self, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '3',
            'msg': 'This step should create an exception.',
            'comment': ''
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name,
                                  step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:
            raise Exception('This exception is intentionally.')
        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        return summary

    # EXECUTE ALL STEPS AUTOMATED --------------------------------------------------------------------------------------
    def run(self, ccs, pool_name, save_pool=True, loglevel='DEBUG', make_new_log_file=True):
        """
        Executes the steps of this test. Before running the steps the preconditions are checked.
        :param ccs: packets.CCScom
            Instance of the class packets.CCScom
        :param pool_name: str
            Name of the datapool for TM/TCs in the database
        :param save_pool: bool
            Set to False if the pool should not be saved e.g.: when this test is done at the end of another test.
        :param loglevel: str
            Defines the log level
        :param make_new_log_file: bool
            The logging writes to a file. If this variable is set to True, a new log-file is created.
        :return: instance of TestIASW66
            A instance of this test class
        """
        testing_logger.cmd_log_handler(__name__)

        # log the header of this test
        report.write_log_test_header(test=self, ccs=ccs, pool_name=pool_name)

        # preconditions of the test
        logger.info('Preconditions: {}'.format(self.precondition))
        # self.precond_ok = self.establish_preconditions(ccs=ccs, pool_name=pool_name)

        # if preconditions are met, execute the steps and note the results
        if True:
            # define the steps array
            steps = [
                self.step_1,
                self.step_2,
                self.step_3
            ]
            self.number_of_steps = len(steps)
            # execute all test steps
            for step in steps:
                try:
                    # run a single step
                    t_start = time.time()
                    res = step(ccs=ccs, pool_name=pool_name)
                    t_end = time.time()
                    logger.debug('runtime of step: {}s\n'.format(t_end - t_start))
                except Exception as error:
                    self.test_passed = False
                    res = report.StepSummary(step_number=step.__name__, result=False)
                    self.exceptions.append(sys.exc_info())
                    logger.critical('Exception in {}'.format(step))
                    logger.exception(error)
                    break
                finally:
                    # add the summary of the step to the result array
                    self.step_results.append(res)
        else:
            logger.error('Preconditions could not be established. Test steps were not executed!\n')

        # save the packet pool
        self.save_pool_in_file(ccs=ccs, pool_name=pool_name, save_pool=save_pool)

        # log the summary of this test
        self.successful_steps = report.write_log_test_footer(test=self)

        # this test has passed, if no Exception occoured, all steps were successful and the integrity is intact
        if self.test_passed is not False:
            if self.successful_steps == self.number_of_steps:
                self.test_passed = True

        return self

    def save_pool_in_file(self, ccs, pool_name, save_pool):
        if save_pool is True:
            pool_file = tools.get_path_for_testing_logs(ccs=ccs) + self.id + '.tmpool'
            ccs.savepool(filename=pool_file, pool_name=pool_name)


# load the configuration file
if 'cfg' not in globals():
    cfg = tools.read_config()
# create a instance of  the PUSDatapoolManager
if 'poolmanager' not in globals():
    logger.debug('Creating a instance of PUSDatapoolManager')
    poolmanager = pus_datapool.PUSDatapoolManager(cfg=cfg)
# create a instance of CCScom
if 'ccs' not in globals():
    logger.debug('Creating a instance of CCScom')
    ccs = packets.CCScom(cfg=cfg, poolmgr=poolmanager)


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
time.sleep(5)

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

# create a instance of the test and the verification
one = ExampleOne(do_verification=False)
two = ExampleTwo(do_verification=False)




print('do: one 1')
evt = threading.Event()
one_1 = threading.Thread(target=one.step_1, args=(evt, ), kwargs={'ccs': ccs, 'pool_name': pool_name}, daemon=False)


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, name):
        super(StoppableThread, self).__init__()
        self.name = name
        self._stop_event = threading.Event()
        self.evt = threading.Event()

        self.child_thread = None

    def stop(self):
        self._stop_event.set()
        print('/\/\/\/\/\/\/\/\ StoppableThread: stop: the event was SET')
        self.child_thread.join()

    def stopped(self):
        print('StoppableThread: stop: _stop_event.is_set() = {}'.format(self._stop_event.is_set()))
        return self._stop_event.is_set()

    def run(self):
        self.child_thread = threading.Thread(target=one.step_1,
                                             name='ExampleOne',
                                             args=(self.evt, ),
                                             kwargs={'ccs': ccs, 'pool_name': pool_name},
                                             daemon=False)
        self.child_thread.start()
        j = 0
        while True:
            print('StoppableThread: run: loop count = {}; stopped: {}'.format(j, self.stopped()))
            j += 1
            if not self.stopped():
                time.sleep(1)
            else:
                self.evt.set()
                print('RETURNING')
                break


a = threading.active_count()
print('a = {}'.format(a))
x = StoppableThread(name='StopMeStopYou')
x.start()
print('x alive: {}'.format(x.is_alive()))
x.stop()
print('x alive: {}'.format(x.is_alive()))
b = threading.active_count()
print('b = {}'.format(b))


one_1.start()
# print('do: one 2')
# threading.Thread(target=one.step_2, kwargs={'ccs': ccs, 'pool_name': pool_name}, daemon=True).start()
# print('do: one 3')
# threading.Thread(target=one.step_3, kwargs={'ccs': ccs, 'pool_name': pool_name}, daemon=True).start()
#
#
# print('do: two 1')
# threading.Thread(target=two.step_1, kwargs={'ccs': ccs, 'pool_name': pool_name}, daemon=True).start()
# print('do: two 2')
# threading.Thread(target=two.step_2, kwargs={'ccs': ccs, 'pool_name': pool_name}, daemon=True).start()
# print('do: two 3')
# threading.Thread(target=two.step_3, kwargs={'ccs': ccs, 'pool_name': pool_name}, daemon=True).start()


