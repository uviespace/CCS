    # VERIFY EVERY STEP ------------------------------------------------------------------------------------------------
    def step_verification(self, pool_name, step_start_cuc, param, summary, ver_file, ver_class, ver_func, step_id, cvars):
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
                success = ver_func_call(pool_name, start_cuc=step_start_cuc, run_id=self.run_id, step_id=step_id, cvars=cvars)
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
        self.check_run_and_step_id(pool_name=pool_name)
        postcon_descr = '$TestPostconDescr'
        success = False
        logger.info('establishing postconditions started')

        $TestPostconEntry

        logger.info('establishing postconditions finished')
        report.write_postcondition_outcome(success, self.run_id, postcon_descr)
        return success

