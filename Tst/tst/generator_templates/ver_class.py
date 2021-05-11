class ${testSpecClassName}Verification:
    def __init__(self):
        self.id = '$testSpecFileName'
        self.name = '$testSpecName'
        self.description = '$testSpecDescription'
        self.precondition = ''
        self.comment = ''
        self.number_of_steps = None
        self.successful_steps = 0
        self.step_results = []
        self.test_passed = None
        self.precond_ok = False
        self.integrity = True
        self.exceptions = []

        # some tests are depended on other tests, thus information is stored on class level
        # insert class variables here

    @staticmethod
    def version():
        return '${testSpecVersion}'

    def verify(self, command_log_file, saved_pool_file):
        """ Used to verify a test afterward it was run. The command log file and the saved pool file are needed.
        :param str command_log_file: log file of the command script
        :param str saved_pool_file: file where the pool was saved
        """
        assert os.path.isfile(os.path.realpath(command_log_file)) is True
        assert os.path.isfile(os.path.realpath(saved_pool_file)) is True

        # ------- load pool from a file -------
        # load the tmpool file into the database
        if not cfl.is_open('poolviewer'):
            logger.error('Poolviewer has to be running to manually verify steps')
            return
        pv = cfl.dbus_connection('poolviewer')
        cfl.Functions(pv, 'load_pool', filename=saved_pool_file)
        pool_name = cfl.Variables(pv, 'active_pool_info')[0]

        # ------- analyze command log -> get step start CUC timestamps, TCid and step end CUC timestamps -------
        # ToDo
        steps = analyse_command_log.get_steps(filename=command_log_file)
        tcs = analyse_command_log.get_sent_tcs(filename=command_log_file)
        # ------- loop over the verification steps, show progress -------
        # ToDo
        # ------- show final result -------
        # ToDo
