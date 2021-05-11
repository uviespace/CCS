    # STEP $testStepNumber --------------------------------------------------------------------------------------------------------
    def step_$testStepNumber(self, pool_name, start_cuc=None, tc_id=None):
        testing_logger.ver_log_handler(__name__)
        param = {
            'step_no': '$testStepNumber',
            'msg': '$testStepDescription',
            'comment': '$testStepComment'
        }
        step_start_cuc = cfl.get_last_pckt_time(pool_name=pool_name, string=False)
        report.verification_step_begin(step_param=param, script_version=self.version(), pool_name=pool_name, step_start_cuc=step_start_cuc)
        # if online: use provided timestamp when the step started, use provided TcId
        if start_cuc is not None:
            pass
        # if offline: read the command log file and extract the starting timestamp and TcId
        else:
            pass

        result = True
        try:
            $testStepVerificationCode
        except Exception as e:
            report.verification_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            result = False
        finally:
            step_end_cuc = cfl.get_last_pckt_time(pool_name=pool_name, string=False)
            report.verification_step_end(step_param=param, step_result=result, step_end_cuc=step_end_cuc)
        return result
