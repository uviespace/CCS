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
        self.precond_ok = self.establish_preconditions(ccs=ccs, pool_name=pool_name)

        # if preconditions are met, execute the steps and note the results
        if self.precond_ok:
            # define the steps array
            steps = [$testStepsList
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
