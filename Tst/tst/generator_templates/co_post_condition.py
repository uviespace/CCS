    # POST-CONDITION ---------------------------------------------------------------------------------------------------
    def post_condition(self, ccs, pool_name):
        """
        Set the period and enable-status of all housekeepings back to their default value.

        :param (packets.CCScom) ccs: Instance of the class packets.CCScom
        :param (str) pool_name: Name of the datapool for TM/TCs in the database

        :return: True if all conditions were successfull.
        :rtype: bool
        """
        testing_logger.cmd_log_handler(__name__)
        result = False

        # reset all housekeepings to their default period and enable status
        reset = tc.reset_all_housekeepings(ccs=ccs, pool_name=pool_name)

        # add further conditions here

        # evaluation if the all conditions are fulfilled
        if reset:
            result = True

        # logging of the result
        if result is True:
            logger.info('+++ POSTCONDITIONS established successful +++')
        else:
            logger.info('failed to establish the post conditions')

        return result
