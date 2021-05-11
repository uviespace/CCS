    # PRECONDITION -----------------------------------------------------------------------------------------------------
    def establish_preconditions(self, pool_name):
        """
        This functions holds the code which prepares the environment for the test.
        :param pool_name: str
            Name of the datapool for TM/TCs in the database
        :return: bool
            True if the preconditions are fulfilled
        """
        #testing_logger.cmd_log_handler(__name__)
        success = False
        logger.info('establishing preconditions started')

        $testpreconentry

        logger.info('establishing preconditions finished')
        report.write_precondition_outcome(success)
        return success
