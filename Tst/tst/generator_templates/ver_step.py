    # STEP $testStepNumber --------------------------------------------------------------------------------------------------------
    def step_$testStepNumber(self, pool_name, start_cuc=None, run_id=None, step_id=None, cvars=None):
        testing_logger.ver_log_handler(__name__)
        param = {
            'step_no': '$testStepNumber',
            'descr': '$testStepDescription',
            'vrc_descr': '$testStepVerificationDescription'
        }
        self.vrc_step_begin(pool_name=pool_name, param=param, run_id=run_id, step_id=step_id)

        result = True
        try:
            $testStepVerificationCode
        except Exception as e:
            report.verification_step_exception(step_param=param, step_id=step_id)
            logger.exception('Exception in the try block of the step')
            result = False
        finally:
            step_end_cuc = cfl.get_last_pckt_time(pool_name=pool_name, string=False)
            report.verification_step_end(step_param=param, step_result=result, step_end_cuc=step_end_cuc, step_id=step_id)
        return result
