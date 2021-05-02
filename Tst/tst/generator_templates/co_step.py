    # STEP ${testStepNumber} --------------------------------------------------------------------------------------------------------
    def step_${testStepNumber}(self, ccs, pool_name):
        testing_logger.cmd_log_handler(__name__)
        param = {
            'step_no': '$testStepNumber',
            'msg': '$testStepDescription',
            'comment': '$testStepComment'
        }
        step_start_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
        report.command_step_begin(step_param=param, script_version=self.version(), ccs=ccs, pool_name=pool_name, step_start_cuc=step_start_cuc)

        summary = report.StepSummary(step_number=param['step_no'])
        tc_id = None
        try:
            $testStepCommandCode
        except Exception as e:
            report.command_step_exception(step_param=param)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = ccs.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc)

        if self.do_verification:
            # execute the verification function for this step from the verification script
            logger.info('Doing verification for step {}'.format(param['step_no']))
            try:
                instance = ${testSpecFileName}_verification.${testSpecClassName}Verification()
                success = instance.step_${testStepNumber}(ccs, pool_name, start_cuc=step_start_cuc, tc_id=tc_id)
                summary.result = success
            except:
                logger.exception('Exception in the Verification for Step {}'.format(param['step_no']))
            finally:
                testing_logger.cmd_log_handler(__name__)
        return summary
