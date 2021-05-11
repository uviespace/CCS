class ${testSpecClassName}:
    def __init__(self, do_verification=False):
        self.id = '${testSpecFileName}'
        self.name = '${testSpecName}'
        self.description = '${testSpecDescription}'
        self.precondition = ''
        self.postcondition = ''
        self.comment = ''
        self.number_of_steps = None
        self.successful_steps = 0
        self.step_results = []
        self.test_passed = None
        self.precond_ok = False
        self.postcond_ok = False
        self.integrity = True
        self.exceptions = []
        self.do_verification = do_verification

        # some tests are depended on other tests, thus information is stored on class level
        # insert class variables here

    @staticmethod
    def version():
        return '${testSpecVersion}'
