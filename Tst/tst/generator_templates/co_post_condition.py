    # POST-CONDITION ---------------------------------------------------------------------------------------------------
    def post_condition(self, pool_name):
        """
        Set the period and enable-status of all housekeepings back to their default value.

        :param (str) pool_name: Name of the datapool for TM/TCs in the database

        :return: True if all conditions were successfull.
        :rtype: bool
        """
        # testing_logger.cmd_log_handler(__name__)
        success = False
        logger.info('establishing postconditions started')

        $testpostconentry

        logger.info('establishing postconditions finished')
        report.write_postcondition_outcome(success)
        return success

