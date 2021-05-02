    # PRECONDITION -----------------------------------------------------------------------------------------------------
    def establish_preconditions(self, ccs, pool_name):
        """
        This functions holds the code which prepares the environment for the test.
        :param ccs: packets.CCScom
            Instance of the class packets.CCScom
        :param pool_name: str
            Name of the datapool for TM/TCs in the database
        :return: bool
            True if the preconditions are fulfilled
        """
        testing_logger.cmd_log_handler(__name__)
        success = False

        # log the current states
        expected_states = {
            'iaswState': 'STANDBY',
            'semState': None,
            'semOperState': None,
            'sdbState': None
        }
        logger.info('establish_preconditions: current states are')
        tm.get_hk_entry(ccs=ccs, pool_name=pool_name, hk_name='IFSW_HK', name=expected_states)

        precond.iasw_standby(ccs=ccs, pool_name=pool_name, silent=True)

        states = tm.get_hk_entry(ccs=ccs, pool_name=pool_name, hk_name='IFSW_HK', name=expected_states, silent=True)
        success = tools.entry_is_equal(entry=states, key_value=expected_states)

        report.write_precondition_outcome(success)
        return success
