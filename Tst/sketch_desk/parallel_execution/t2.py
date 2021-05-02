import logging
import sys
import os
import time
import importlib
import multiprocessing
from testlib import tools
from testlib import report
from testlib import tm
from testlib import tc
from testlib import tcid
from testlib import precond
from testlib import testing_logger
from testlib import sim

# create logger
logger = logging.getLogger(__name__)

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
    def step_1(self, ccs, pool_name, queue, configurer, event, *args):
        configurer(queue)
        logger = logging.getLogger(__name__)
        #testing_logger.cmd_log_handler(__name__)
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
            while True:
                logger.info('example_2: step_1: event_is_set = {}, count = {}'.format(event.is_set(), i))
                if event.is_set():
                    logger.warning('Event was set: {}'.format(event.is_set))
                    break
                time.sleep(0.5)
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
