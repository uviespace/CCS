class ${testSpecClassName}:
    def __init__(self, do_verification=False):
        self.id = '${testSpecFileName}'
        self.name = '${testSpecName}'
        self.spec_version = '${testSpecVersion}'
        self.iasw_version = '${testIaswVersion}'
        self.description = '${testSpecDescription}'
        self.precondition = '${testPreCondition}'
        self.postcondition = '${testPostCondition}'
        self.comment = '${testComment}'
        self.number_of_steps = None
        self.successful_steps = 0
        self.step_results = []
        self.test_passed = None
        self.precond_ok = False
        self.postcond_ok = False
        self.integrity = True
        self.exceptions = []
        self.do_verification = do_verification
        self.run_id = False

        # some tests are depended on other tests, thus information is stored on class level
        # insert class variables here
