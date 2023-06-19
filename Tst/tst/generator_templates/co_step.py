    # STEP ${testStepNumber} --------------------------------------------------------------------------------------------------------
    def step_${testStepNumber}(self, pool_name):
        param = {
            'step_no': '$testStepNumber',
            'descr': '$testStepDescription',
            'comment': '$testStepComment'
        }
        step_start_cuc, summary, step_id = self.begin_steps(pool_name=pool_name, param=param)

        try:
            ########---The defined step starts here---########

            $testStepCommandCode

            ########---The defined step ends here---########
        except Exception as e:
            report.command_step_exception(step_param=param, step_id=step_id)
            logger.exception('Exception in the try block of the step')
            summary.result = False
            summary.had_exception()
        finally:
            step_end_cuc = cfl.get_last_pckt_time(pool_name=pool_name, string=False)
            report.command_step_end(step_param=param, step_end_cuc=step_end_cuc, step_id=step_id)

        summary = self.step_verification(pool_name=pool_name, step_start_cuc=step_start_cuc, param=param, summary=summary,
                                         ver_file=${testSpecFileName}_verification, ver_class="${testSpecClassName}Verification",
                                         ver_func="step_${testStepNumber}", step_id=step_id)

        return summary
