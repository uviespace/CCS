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
        self.run_id = False

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
        self.run_id = False
        steps = analyse_command_log.get_steps(filename=command_log_file)
        tcs = analyse_command_log.get_sent_tcs(filename=command_log_file)
        # ------- loop over the verification steps, show progress -------
        # ToDo
        # ------- show final result -------
        # ToDo

    def vrc_step_begin(self, pool_name, param, run_id, step_id):
        if run_id:
            self.run_id = run_id
        else:
            if not self.run_id:
                now = datetime.now()  # current date and time
                self.run_id = now.strftime("%Y%m%d%H%M%S")

        step_start_cuc = cfl.get_last_pckt_time(pool_name=pool_name, string=False)
        report.verification_step_begin(step_param=param, script_version=self.version(), pool_name=pool_name,
                                       step_start_cuc=step_start_cuc, run_id=self.run_id, step_id=step_id)
