    # VERIFY EVERY STEP ------------------------------------------------------------------------------------------------
    def step_verification(self, pool_name, step_start_cuc, param, summary, tc_id, ver_file, ver_class, ver_func, step_id):
        """
        This functions does the verification for every step
        :param pool_name: str
            Name of the datapool for TM/TCs in the database
        :param step_start_cuc: time
            Time when the step started
        :param param: list
            Includes the parameters of the step
        :param summary: report.StepSummary class object
            Containes a summary of the test
        :param tc_id:
        :param ver_instance: class Instance definition
            If called the verification class is initialized
        :param ver_instance: func
            If called the verification function is called
        :return: summary :report.StepSummary class object
            Containes a summary of the test
        """
        if self.do_verification:
            # execute the verification function for this step from the verification script
            logger.info('Doing verification for step {}'.format(param['step_no']))
            try:
                ver_instance_call = getattr(ver_file, ver_class)
                instance = ver_instance_call()
                ver_func_call = getattr(instance, ver_func)
                success = ver_func_call(pool_name, start_cuc=step_start_cuc, tc_id=tc_id, run_id=self.run_id, step_id=step_id)
                summary.result = success
            except:
                logger.exception('Exception in the Verification for Step {}'.format(param['step_no']))
            finally:
                testing_logger.cmd_log_handler(__name__)

        return summary

    # POST-CONDITION ---------------------------------------------------------------------------------------------------
    def post_condition(self, pool_name):
        """
        Set the period and enable-status of all housekeepings back to their default value.

        :param (str) pool_name: Name of the datapool for TM/TCs in the database

        :return: True if all conditions were successfull.
        :rtype: bool
        """
        testing_logger.cmd_log_handler(__name__)
        success = False
        logger.info('establishing postconditions started')

        $testpostconentry

        logger.info('establishing postconditions finished')
        report.write_postcondition_outcome(success)
        return success

