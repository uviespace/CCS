"""
Data model of a test specification.
A instance of a test case consists out of

    * test case information
    * the steps

The numeration of the steps consists out ouf a primary counter and a secondary counter, separated by a dot (e.g. 2.1).
Although this approach may look like a grouping, it is not intended to be. It is more a history preservation if the test
altered after an official delivery.

Features:

    * adding a step

        * adding a step above (:py:meth:`~test_specification.TestSequence.add_step_above`)
        * adding a step below (:py:meth:`~test_specification.TestSequence.add_step_below`)

    * removing a step (:py:meth:`~test_specification.TestSequence.remove_step`)
    * renumber the steps (decrease_step_numbers, increase_step_numbers)

        * :py:func:`~test_specification.TestSequence.decrease_step_numbers`
        * :py:func:`~test_specification.TestSequence.increase_step_numbers`

    * Lock-mechanism for the numeration of the steps.

        * If a test is locked:

            * the primary counter of a step is "frozen", new steps get numerated using the secondary counter
            * the behaviour of adding a step is changed
            * deleting a step is not possible anymore

        * if a test is unlocked:

            * re-numeration for all steps should be possible only manually

    * generating a JSON string out of the data (encode_to_json, serialize)

        * :py:func:`~test_specification.TestSequence.encode_to_json`
        * :py:func:`~test_specification.TestSequence.serialize`

    * creating a instance from a JSON string (decode_to_json)

        * :py:func:`~test_specification.TestSequence.decode_to_json`

Parallel processes:
A test can have parallel processes. To mark if a step is has the attribute 'sequence'. The different sequences are
numbered, starting at 0. To start a sequence a step should be made and a function should be called.
"""
import json
import copy
import logging
import os
import gettext
import unittest
import confignator
import toolbox

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.WARNING)
console_hdlr = toolbox.create_console_handler(hdlr_lvl=logging.WARNING)
logger.addHandler(hdlr=console_hdlr)

# using gettext for internationalization (i18n)
localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'locale')
translate = gettext.translation('handroll', localedir, fallback=True)
_ = translate.gettext


def create_step_number(primary_counter: int, secondary_counter: int) -> str:
    """
    Using integers to build a string consisting of primary counter and secondary counter, which are separated by a dot.

    :param int primary_counter: the primary counter of the step
    :param int secondary_counter: the secondary counter of the step
    :return: the step number as a string (<primary_counter>.<secondary_counter>
    :rtype: str
    """
    assert isinstance(primary_counter, int)
    assert isinstance(secondary_counter, int)
    step_number_string = str(primary_counter) + '.' + str(secondary_counter)
    return step_number_string


def parse_step_number(step_number: (str, int, float)):
    """
    Parses the input value into a tuple of primary counter and secondary counter.

    :param str, int, float step_number: the value which should be a step number
    :return: a tuple consisting out of the primary counter and secondary counter of a step
    :rtype: (int, int)
    """
    assert isinstance(step_number, (str, int, float))
    step_number_string = str(step_number)
    separator = step_number_string.find('.')
    if separator != -1:  # found the separator in the string
        primary_counter = int(step_number_string[:separator])
        secondary_counter = int(step_number_string[separator+1:])
    else:  # did not find the separator in the string
        primary_counter = int(step_number_string)
        secondary_counter = 0

    return primary_counter, secondary_counter


class Step:
    def __init__(self, test_seq=None, step_num=None, prim_counter=None, seco_counter=None, step=None, logger=logger):
        self.logger = logger
        # self._sequence = 0
        self._primary_counter = 0
        self._secondary_counter = 0
        self._step_number = ''
        self._description = ''
        self._command_code = ''
        self._step_comment = ''
        self._verification_code = ''
        self._verification_description = ''
        self._is_active = True
        self._verified_item = []
        self._start_sequence = None
        self._stop_sequence = None
        self.test = test_seq

        # set the step number
        if step_num is not None:
            self.primary_counter = parse_step_number(step_num)[0]
            self.secondary_counter = parse_step_number(step_num)[1]
        if step_num is None and prim_counter is not None:
            self.primary_counter = prim_counter
            if seco_counter is not None:
                self.secondary_counter = seco_counter
            else:
                self.secondary_counter = 0

        # if a json is provided, read the step attributes from it
        if step is not None:
            self.set_attributes_from_json(step)

    def __deepcopy__(self, memodict={}):
        new_step = Step()
        # new_step.sequence = copy.copy(self.sequence)
        new_step.primary_counter = copy.copy(self.primary_counter)
        new_step.secondary_counter = copy.copy(self.secondary_counter)
        new_step.description = copy.copy(self.description)
        new_step.command_code = copy.copy(self.command_code)
        new_step.step_comment = copy.copy(self.step_comment)
        new_step.verification_code = copy.copy(self.verification_code)
        new_step.verification_description = copy.copy(self.verification_description)
        new_step.is_active = copy.copy(self.is_active)
        new_step.start_sequence = copy.copy(self.start_sequence)
        new_step.stop_sequence = copy.copy(self.stop_sequence)
        # new_step._verified_item = copy.copy(self._verified_item)
        return new_step

    # @property
    # def sequence(self):
    #     return self._sequence
    #
    # @sequence.setter
    # def sequence(self, value: int):
    #     assert isinstance(value, int)
    #     self._sequence = value

    @property
    def primary_counter(self):
        return self._primary_counter

    @primary_counter.setter
    def primary_counter(self, value: int):
        assert isinstance(value, int)
        self._primary_counter = value
        self._step_number = str(self.primary_counter) + '.' + str(self.secondary_counter)

    @property
    def secondary_counter(self):
        return self._secondary_counter

    @secondary_counter.setter
    def secondary_counter(self, value: int):
        assert isinstance(value, int)
        self._secondary_counter = value
        self._step_number = str(self.primary_counter) + '.' + str(self.secondary_counter)

    # Do not use if a test file should be generated, Output is always '1.0' and not '1_0'
    # A Point is not supported in a function/method name in python, use 'step_number_test_format' function instead
    @property
    def step_number(self):
        return self._step_number

    @step_number.setter
    def step_number(self, value: str):
        assert isinstance(value, (str, int))
        if isinstance(value, str):
            # verify, that the format of primary.secondary (e.g.: 1.1, 1.2, ...) is fulfilled
            primary, secondary = parse_step_number(value)
            self._step_number = value
        if isinstance(value, int):
            self._step_number = str(value)

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value: str):
        assert isinstance(value, str)
        self._description = value

    @property
    def command_code(self):
        return self._command_code

    @command_code.setter
    def command_code(self, value: str):
        assert isinstance(value, str)
        self._command_code = value

    @property
    def step_comment(self):
        return self._step_comment

    @step_comment.setter
    def step_comment(self, value: str):
        assert isinstance(value, str)
        self._step_comment = value

    @property
    def verification_code(self):
        return self._verification_code

    @verification_code.setter
    def verification_code(self, value: str):
        assert isinstance(value, str)
        self._verification_code = value

    @property
    def verification_description(self):
        return self._verification_description

    @verification_description.setter
    def verification_description(self, value: str):
        assert isinstance(value, str)
        self._verification_description = value

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool):
        assert isinstance(value, bool)
        self._is_active = value

    @property
    def start_sequence(self):
        return self._start_sequence

    @start_sequence.setter
    def start_sequence(self, value: int):
        assert isinstance(value, int) or value is None
        self._start_sequence = value

    @property
    def stop_sequence(self):
        return self._stop_sequence

    @stop_sequence.setter
    def stop_sequence(self, value: int):
        assert isinstance(value, int) or value is None
        self._stop_sequence = value

    @property
    def step_number_test_format(self):
        primary = parse_step_number(self._step_number)[0]
        secondary = parse_step_number(self._step_number)[1]
        return str(primary) + '_' + str(secondary)

    def set_attributes_from_json(self, step):
        """
        Loading the step attributes from a parsed JSON file.

        :param: dict step: a dictionary parsed from a JSON file containing the information of a step
        """
        try:
            # self.sequence = step['_sequence']
            self.primary_counter = step['_primary_counter']
            self.secondary_counter = step['_secondary_counter']
            self.description = step['_description']
            self.command_code = step['_command_code']
            self.step_comment = step['_step_comment']
            self.verification_code = step['_verification_code']
            self.verification_description = step['_verification_description']
            self.is_active = step['_is_active']
        except KeyError as error:
            self.logger.error('KeyError: no {} could be found in the loaded data'.format(error))
        # load optional attributes
        try:
            self.start_sequence = step['_start_sequence']
            self.stop_sequence = step['_stop_sequence']
        except KeyError:
            pass
        return

    def increase_primary_counter(self):
        current_step_number = self.step_number
        self.primary_counter = self.primary_counter + 1
        self.logger.debug('increased step number: {} -> {}'.format(current_step_number, self.step_number))
        return

    def decrease_primary_counter(self):
        current_step_number = self.step_number
        self.primary_counter = self.primary_counter - 1
        self.logger.debug('decreased step number: {} -> {}'.format(current_step_number, self.step_number))
        return

    def increase_secondary_counter(self):
        current_step_number = self.step_number
        self.secondary_counter = self.secondary_counter + 1
        own_list_index = self.test.get_step_index(self.step_number)
        self.logger.debug('increased step number: {} -> {} (index: {})'.format(current_step_number, self.step_number, own_list_index))
        return

    def decrease_secondary_counter(self):
        current_step_number = self.step_number
        self.secondary_counter = self.secondary_counter - 1
        self.logger.debug('decreased step number: {} -> {}'.format(current_step_number, self.step_number))
        return


class TestSequence:
    def __init__(self, sequence=0, json_data=None, logger=logger):
        """
        Creates a new instance of TestSequence. If a JSON object was provided it will be decoded and used otherwise
        an empty instance is created.
        For every attribute there is a function to set its value.
        :param json_data: the JSON object which is used to build the test specification
        """
        self.logger = logger
        self._sequence = sequence
        self._name = ''
        self._description = ''
        self._spec_version = ''
        self._primary_counter_locked = False
        self.steps = []

        if json_data is not None:
            # load from a JSON and then sort the steps by their step number and verify the numbering
            self.decode_from_json(json_data)
            self.resort_step_list_by_step_numbers()
            self.verify_step_list_consistency()

    def __deepcopy__(self):
        new_test_seq = TestSequence()
        new_test_seq.sequence = copy.copy(self.sequence)
        new_test_seq.name = copy.copy(self.name)
        new_test_seq.description = copy.copy(self.description)
        new_test_seq.spec_version = copy.copy(self.spec_version)
        new_test_seq.primary_counter_locked = copy.copy(self.primary_counter_locked)
        new_test_seq.steps = copy.deepcopy(self.steps)

        return new_test_seq

    @property
    def primary_counter_locked(self):
        return self._primary_counter_locked

    @primary_counter_locked.setter
    def primary_counter_locked(self, value: bool):
        assert isinstance(value, bool)
        self._primary_counter_locked = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value: str):
        assert isinstance(value, str)
        self._name = value

    @property
    def sequence(self):
        return self._sequence

    @sequence.setter
    def sequence(self, value: int):
        assert isinstance(value, int)
        self._sequence = value

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value: str):
        assert isinstance(value, str)
        self._description = value

    @property
    def spec_version(self):
        return self._spec_version

    @spec_version.setter
    def spec_version(self, value: str):
        assert isinstance(value, str)
        self._spec_version = value

    def verify_step_list_consistency(self) -> bool:
        """
        Testing the step list for integrity. The step numbers have to increase steadily without gaps.

        :return: If the step list is consistent, True is returned
        :rtype: bool
        """
        try:
            for idx, stp in enumerate(self.steps):
                if idx == 0:
                    # the first item in the list has to be the step 1.0
                    assert(stp.primary_counter == 1)
                    assert(stp.secondary_counter == 0)
                else:
                    last_stp = self.steps[idx - 1]
                    # verify that the step numbers are steadily increasing and are uninterrupted
                    if last_stp.primary_counter == stp.primary_counter:
                        # the secondary counter is greater than the last one
                        assert(stp.secondary_counter > last_stp.secondary_counter)
                        # the difference is 1
                        assert(stp.secondary_counter - last_stp.secondary_counter == 1)
                    else:
                        # the primary counter is greater than the last one
                        assert(stp.primary_counter > last_stp.primary_counter)
                        # the difference is 1
                        assert(stp.primary_counter - last_stp.primary_counter == 1)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def resort_step_list_by_step_numbers(self):
        """
        The list of the steps is sorted by the step number.
        """
        # sort by secondary counter
        s = sorted(self.steps, key=lambda step: step.secondary_counter)
        # sort by primary counter
        p = sorted(s, key=lambda step: step.primary_counter)
        # assign the sorted step list
        self.steps = p

    def highest_step_number(self) -> str:
        """
        Returns the step number with the highest step number. This is achieved by first sorting the step list, then
        return the last element in the list
        :return: step number of the last step
        :rtype: str
        """
        self.resort_step_list_by_step_numbers()
        return self.steps[-1].step_number

    def log_list_of_steps(self):
        self.logger.debug('--------------------------------------------')
        self.logger.debug('List of steps:')
        if len(self.steps) > 0:
            for index, step in enumerate(self.steps):
                self.logger.debug('Step {},{} (index: {}, id:{})'.format(step.primary_counter, step.secondary_counter, index, id(step)))
        else:
            self.logger.debug('list of steps is empty')
        self.logger.debug('--------------------------------------------')

    def get_step_index(self, step_number: (str, int, float)):
        """
        Retrieves, for a given step_number, the index of the step in the step list.
        Raises LookupError if the step_number has no matching step in the list.

        :param str, int, float step_number: number of the desired step
        :return: index of the desired step
        :rtype: int
        """
        assert isinstance(step_number, (str, int, float))
        # find the index within the list of the step
        index_ref_step = None
        primary, secondary = parse_step_number(step_number)
        for ndx, step in enumerate(self.steps):
            if step.primary_counter == primary:
                if step.secondary_counter == secondary:
                    index_ref_step = ndx
        if index_ref_step is None:
            raise LookupError
        else:
            return index_ref_step

    def get_step(self, step_number: (str, int, float)):
        """
        Retrieves, for a given step_number, the step object

        :param str, int, float step_number: number of the desired step
        :return: The step instance.
        :rtype: data_model.Step
        """
        step_index = self.get_step_index(step_number)
        step = self.steps[step_index]
        return step

    def add_step_above(self, reference_step_position):
        """
        Determines the step number of the step to add.  then adds a step above the step provided as argument
        :param reference_step_position: the step which is the reference for adding a new step above
        :return:
        """
        # figure out the primary and secondary counter of the new step
        try:
            # get index of the reference step
            index_ref_step = self.get_step_index(reference_step_position)
            ref_step = self.steps[index_ref_step]
            index_new_step = index_ref_step
            try:
                # get the step before the reference step
                before_step = self.steps[index_ref_step - 1]
            except IndexError:
                before_step = None

            # determine the primary and secondary counter of the new step
            if before_step is None or (before_step.secondary_counter == 0 and not self.primary_counter_locked):
                new_step_primary = ref_step.primary_counter
                new_step_secondary = 0
            else:
                new_step_primary = before_step.primary_counter
                new_step_secondary = before_step.secondary_counter + 1
        except LookupError:
            if len(self.steps) == 0:  # edge-case: the step list is empty
                index_new_step = 0
                new_step_primary = 1
                new_step_secondary = 0
            else:
                self.logger.error('step {} could not be found, thus no step is added below'.format(reference_step_position))
                return

        # create the new step
        number_new_step = create_step_number(new_step_primary, new_step_secondary)
        new_step = Step(step_num=number_new_step, test_seq=self)

        # add the new step to the list - the new step takes the place below the reference step

        self.steps.insert(index_new_step, new_step)
        self.logger.debug(
            'added Step {}.{} (index: {}, id:{})'.format(new_step.primary_counter, new_step.secondary_counter, index_new_step, id(new_step)))

        # increase the step numbers of the following steps
        for step in self.steps[index_new_step + 1:]:
            if step.primary_counter == new_step.primary_counter and new_step.secondary_counter > 0:
                step.increase_secondary_counter()
            elif not self.primary_counter_locked:
                step.increase_primary_counter()

        return new_step

    def add_step_below(self, reference_step_position=None, step_instance=None):
        # figure out the primary and secondary counter of the new step
        if reference_step_position is None and len(self.steps) == 0:
            # edge-case: the step list is empty
            index_new_step = 0
            new_step_primary = 1
            new_step_secondary = 0
        else:
            # the step list is not empty, thus find the reference step and the following
            if reference_step_position is None:   # append it
                index_ref_step = -1
            else:
                try:
                    # get the reference step
                    index_ref_step = self.get_step_index(reference_step_position)
                except LookupError:
                    # Although the list of steps is not empty, no reference step could be found (for whatever reason).
                    raise Exception
            ref_step = self.steps[index_ref_step]
            index_ref_step = self.get_step_index(ref_step.step_number)  # if the index was -1, get the actual index
            index_new_step = index_ref_step + 1

            # get the next step
            if index_ref_step is not None:
                try:
                    # get the following step of reference step
                    next_step = self.steps[index_ref_step + 1]
                except IndexError:
                    next_step = None
            else:
                next_step = None

            # determine the primary and secondary counter of the new step
            if next_step is None or (next_step.secondary_counter == 0 and not self.primary_counter_locked):
                new_step_primary = ref_step.primary_counter + 1
                new_step_secondary = 0
            else:
                new_step_primary = ref_step.primary_counter
                new_step_secondary = ref_step.secondary_counter + 1

        # create the new step
        number_new_step = create_step_number(new_step_primary, new_step_secondary)
        if step_instance is None:
            # make a new Step
            new_step = Step(step_num=number_new_step, test_seq=self)
        else:
            # use the provided Step
            assert isinstance(step_instance, Step)
            new_step = step_instance
            new_step.primary_counter = new_step_primary
            new_step.secondary_counter = new_step_secondary

        # add the new step to the list - the new step takes the place below the reference step
        self.steps.insert(index_new_step, new_step)
        self.logger.debug('added Step {}.{} (index: {}, id:{})'.format(new_step.primary_counter, new_step.secondary_counter, index_new_step, id(new_step)))

        # increase the step numbers of the following steps
        for step in self.steps[index_new_step + 1:]:
            if step.primary_counter == new_step.primary_counter and new_step.secondary_counter > 0:
                step.increase_secondary_counter()
            elif not self.primary_counter_locked:
                step.increase_primary_counter()

        return new_step

    def remove_step(self, step_number: (str, int, float)):
        """
        Deletes a step out of the dictionary for steps. If the step is found, decrease all the following step numbers,
        then delete the step.
        :param str, int, float step_number: The step which will be deleted
        """
        try:
            # get index within the step list of the step
            index_of_step = self.get_step_index(step_number)
        except LookupError:
            self.logger.error('step {} could not be found, thus no step is added below'.format(step_number))
            return

        # decrease step numbers if step has following steps
        self.decrease_step_numbers(reference_step_number=step_number)

        # delete the step in the list
        self.steps.pop(index_of_step)
        self.logger.debug('deleted Step {} (index: {})'.format(step_number, index_of_step))

        return

    def move_step(self, step_to_move_index: int, desired_position_index: int):
        """
        Moving a step within the data model. A step can be moved upward or downward.
        Cases:

        * step_to_move < desired_position


        * step_to_move == desired_position

            * do nothing

        * step_to_move > desired_position

        :param int step_to_move_index: index in the list of the step which should be moved
        :param int desired_position_index: index in the list of the moved step after the move
        """
        assert isinstance(step_to_move_index, int)
        assert isinstance(desired_position_index, int)
        if desired_position_index == -1:
            # prevent unexpected behavior if the desired position is before the first item (which has index 0)
            desired_position_index = 0
        self.logger.debug('list of steps before moving:')
        self.log_list_of_steps()

        if step_to_move_index < desired_position_index:  # move the step downwards
            # get the step, which should be moved
            step_to_move = self.steps[step_to_move_index]
            assert isinstance(step_to_move, Step)
            # decrease the step counters, since the step gets removed
            self.decrease_step_numbers(reference_step_index=step_to_move_index)
            # delete the step from the list
            logger.debug('delete the step which is moved from the list')
            self.steps.pop(step_to_move_index)

            # figure out the which step number to reassign to the step (it was moved, thus it gets a new step number)
            stored_step_number = step_to_move.step_number
            if desired_position_index > 0:
                try:
                    step_before = self.steps[desired_position_index-1]
                except IndexError:
                    step_before = self.steps[-1]
                assert isinstance(step_before, Step)
                if self.primary_counter_locked:
                    step_to_move.primary_counter = step_before.primary_counter
                    step_to_move.secondary_counter = step_before.secondary_counter + 1
                else:
                    step_to_move.primary_counter = step_before.primary_counter + 1
                    step_to_move.secondary_counter = 0
            else:
                # it is moved to the top position
                step_to_move.primary_counter = 1
                step_to_move.secondary_counter = 0
            logger.debug('changed step number: {} -> {}'.format(stored_step_number, step_to_move.step_number))
            # insert it again at the desired position (-1, because the indices got decreased when the step was deleted)
            logger.debug('insert the moved step again')
            self.steps.insert(desired_position_index, step_to_move)
            # increase the step numbers, since a step was added
            self.increase_step_numbers(reference_step_index=desired_position_index-1)

        elif step_to_move_index == desired_position_index:
            pass
        elif step_to_move_index > desired_position_index:  # move the step upwards
            # get the step, which should be moved
            step_to_move = self.steps[step_to_move_index]
            assert isinstance(step_to_move, Step)
            # decrease the step counters, since the step is going to be removed
            self.decrease_step_numbers(reference_step_index=step_to_move_index)
            # delete the step from the list
            logger.debug('delete the step which is moved from the list')
            self.steps.pop(step_to_move_index)

            # figure out the which step number to reassign to the step (it was moved, thus it gets a new step number)
            stored_step_number = step_to_move.step_number
            if desired_position_index > 0:
                try:
                    step_before = self.steps[desired_position_index - 1]
                except IndexError:
                    step_before = self.steps[-1]
                assert isinstance(step_before, Step)
                if self.primary_counter_locked:
                    step_to_move.primary_counter = step_before.primary_counter
                    step_to_move.secondary_counter = step_before.secondary_counter + 1
                else:
                    step_to_move.primary_counter = step_before.primary_counter + 1
                    step_to_move.secondary_counter = 0
            else:
                # it is moved to the top position
                step_to_move.primary_counter = 1
                step_to_move.secondary_counter = 0
            logger.debug('changed step number: {} -> {}'.format(stored_step_number, step_to_move.step_number))
            # insert it again at the desired position
            logger.debug('insert the moved step again')
            self.steps.insert(desired_position_index, step_to_move)
            # increase the step numbers, since a step was added
            self.increase_step_numbers(reference_step_index=desired_position_index)

        self.logger.debug('list of steps after moving:')
        self.log_list_of_steps()
        self.verify_step_list_consistency()

    def renumber_steps(self):
        """
        Renumbering all steps. The steps are numerated by only using the primary counter.
        All secondary counters will be set to 0.
        """
        for index, step in enumerate(self.steps):
            if index == 0:
                step.primary_counter = 1
                step.secondary_counter = 0
            else:
                last_step = self.steps[index-1]
                step.primary_counter = last_step.primary_counter + 1
                step.secondary_counter = 0
        return

    def decrease_step_numbers(self, reference_step_number: (str, int, float) = '', reference_step_index: int = None):
        """
        Decreases the step numbers of all steps following the reference step, excluding it.
        This function is used to reassign the step numbers after
        * a step was deleted from the data model
        * a step was moved within the data model

        :param (str, int, float) reference_step_number: the number of the step to start the decreasing (EXCLUDING)
        :param int reference_step_index: the index within the step list of the reference step
        """
        # get the index
        if reference_step_index is None:
            try:
                index_ref_step = self.get_step_index(reference_step_number)
            except LookupError:
                index_ref_step = None
                self.logger.error('could not find the reference step, thus no step numbers where increased')
            except ValueError:
                index_ref_step = None
                self.logger.error('{} is not a valid step number'.format(reference_step_number))
        else:
            index_ref_step = reference_step_index
        # get the step
        try:
            ref_step = self.steps[index_ref_step]
            assert isinstance(ref_step, Step)
        except IndexError or TypeError:
            ref_step = None
            self.logger.error('could not find the reference step, thus no step numbers where increased')
        # decrease the step numbers of the following steps
        for step in self.steps[index_ref_step + 1:]:
            if ref_step.secondary_counter == 0:
                # decrease all following primary counter
                step.decrease_primary_counter()
            else:
                # decrease all following secondary counter for steps,
                # which have the same primary counter as the reference step
                if step.primary_counter == ref_step.primary_counter:
                    step.decrease_secondary_counter()
        return

    def increase_step_numbers(self, reference_step_number: (str, int, float) = '', reference_step_index: int = None):
        """
        Increases the step numbers of all steps following the reference step, excluding it.
        This function is used to reassign the step numbers after
        * a step was added to the data model
        * a step was moved within the data model

        :param (str, int, float) reference_step_number: the number of the step to start the increasing (EXCLUDING)
        :param int reference_step_index: the index within the step list of the reference step
        """
        # get the index
        if reference_step_index is None:
            try:
                index_ref_step = self.get_step_index(reference_step_number)
            except LookupError:
                index_ref_step = None
                self.logger.error('could not find the reference step, thus no step numbers where increased')
            except ValueError:
                index_ref_step = None
                self.logger.error('{} is not a valid step number'.format(reference_step_number))
        else:
            index_ref_step = reference_step_index
        # get the step
        try:
            ref_step = self.steps[index_ref_step]
            assert isinstance(ref_step, Step)
        except IndexError or TypeError:
            ref_step = None
            self.logger.error('could not find the reference step, thus no step numbers where increased')
        # increase the step numbers of the following steps
        if ref_step is not None:
            last_step = ref_step
            for index, step in enumerate(self.steps[index_ref_step + 1:]):
                if step.primary_counter == last_step.primary_counter:
                    if step.secondary_counter != 0 and step.primary_counter == ref_step.primary_counter:
                        step.increase_secondary_counter()
                    if step.secondary_counter == 0:
                        step.increase_primary_counter()
                elif step.secondary_counter != 0:
                    step.increase_primary_counter()
                last_step = step
        return

    def verified_items(self):
        """
        Returns a list of all verified items. The verified items are stored in each step.
        """
        # ToDo
        return

    def encode_to_json(self, *args):
        """
        Makes out of the TestSequence a JSON object.
        """
        json_string = None
        json_string = json.dumps(self, default=self.serialize)
        return json_string

    def decode_from_json(self, json_data: dict):
        """
        Create a TestSequence instance from a JSON object.
        """
        try:
            self.name = json_data['_name']
            self.description = json_data['_description']
            self.spec_version = json_data['_spec_version']
            self.sequence = json_data['_sequence']
        except KeyError as keyerror:
            self.logger.error('KeyError: no {} could be found in the loaded data'.format(keyerror))

        self.steps = []
        try:
            for index, step in enumerate(json_data['steps']):
                self.steps.append(Step(test_seq=self, step=step))
        except KeyError as keyerror:
            self.logger.error('KeyError: no {} could be found in the loaded data'.format(keyerror))
        return

    @staticmethod
    def serialize(obj):
        """
        JSON serializer for objects which are not serializable by default.
        Uses the overwritten __deepcopy__ methods of the classes, to make copies. Then takes the dictionarys of them
        and deletes the objects, which can not be serialized.
        """
        if isinstance(obj, TestSequence):
            obj_copy = obj.__deepcopy__()
            obj_dict = obj_copy.__dict__
            del obj_dict['logger']
            return obj_dict
        if isinstance(obj, Step):
            obj_copy = obj.__deepcopy__()
            obj_dict = obj_copy.__dict__
            del obj_dict['test']
            del obj_dict['logger']
            return obj_dict

class TestSpecification:
    def __init__(self, json_data=None, logger=logger):
        self.logger = logger
        self._name = ''
        self._description = ''
        self._spec_version = ''
        self._iasw_version = ''
        self._primary_counter_locked = False
        self._precon_name = ''
        self._precon_code = ''
        self._precon_descr = ''
        self._postcon_name = ''
        self._postcon_code = ''
        self._postcon_descr = ''
        self._comment = ''
        self._custom_imports = ''
        self.sequences = []

        if json_data is not None:
            # load from a JSON and then sort the steps by their step number and verify the numbering
            self.decode_from_json(json_data)

    def __deepcopy__(self):
        new_testspec = TestSpecification()
        new_testspec.sequences = copy.copy(self.sequences)
        new_testspec.name = copy.copy(self.name)
        new_testspec.description = copy.copy(self.description)
        new_testspec.spec_version = copy.copy(self.spec_version)
        new_testspec.iasw_version = copy.copy(self.iasw_version)
        new_testspec.primary_counter_locked = copy.copy(self.primary_counter_locked)
        new_testspec.precon_name = copy.copy(self.precon_name)
        new_testspec.precon_code = copy.copy(self.precon_code)
        new_testspec.precon_descr = copy.copy(self.precon_descr)
        new_testspec.postcon_name = copy.copy(self.postcon_name)
        new_testspec.postcon_code = copy.copy(self.postcon_code)
        new_testspec.postcon_descr = copy.copy(self.postcon_descr)
        new_testspec.comment = copy.copy(self.comment)
        new_testspec.custom_imports = copy.copy(self.custom_imports)

        return new_testspec

    @property
    def primary_counter_locked(self):
        return self._primary_counter_locked

    @primary_counter_locked.setter
    def primary_counter_locked(self, value: bool):
        assert isinstance(value, bool)
        self._primary_counter_locked = value
        # set the primary_counter_locked for all sequences
        for seq in self.sequences:
            assert isinstance(seq, TestSequence)
            seq.primary_counter_locked = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value: str):
        assert isinstance(value, str)
        self._name = value

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value: str):
        assert isinstance(value, str)
        self._description = value

    @property
    def spec_version(self):
        return self._spec_version

    @spec_version.setter
    def spec_version(self, value: str):
        assert isinstance(value, str)
        self._spec_version = value

    @property
    def iasw_version(self):
        return self._iasw_version

    @iasw_version.setter
    def iasw_version(self, value: str):
        assert isinstance(value, str)
        self._iasw_version = value

    @property
    def precon_name(self):
        return self._precon_name

    @precon_name.setter
    def precon_name(self, value: str):
        if value == None:
            value = "None"
        else:
            pass
        assert isinstance(value, str)
        self._precon_name = value

    @property
    def precon_code(self):
        return self._precon_code

    @precon_code.setter
    def precon_code(self, value: str):
        assert isinstance(value, str)
        self._precon_code = value

    @property
    def precon_descr(self):
        return self._precon_descr

    @precon_descr.setter
    def precon_descr(self, value: str):
        assert isinstance(value, str)
        self._precon_descr = value

    @property
    def postcon_name(self):
        return self._postcon_name

    @postcon_name.setter
    def postcon_name(self, value: str):
        if value == None:
            value = "None"
        else:
            pass
        assert isinstance(value, str)
        self._postcon_name = value

    @property
    def postcon_code(self):
        return self._postcon_code

    @postcon_code.setter
    def postcon_code(self, value: str):
        assert isinstance(value, str)
        self._postcon_code = value

    @property
    def postcon_descr(self):
        return self._postcon_descr

    @postcon_descr.setter
    def postcon_descr(self, value: str):
        assert isinstance(value, str)
        self._postcon_descr = value

    @property
    def comment(self):
        return self._comment

    @comment.setter
    def comment(self, value: str):
        assert isinstance(value, str)
        self._comment = value

    @property
    def custom_imports(self):
        return self._custom_imports

    @custom_imports.setter
    def custom_imports(self, value: str):
        assert isinstance(value, str)
        self._custom_imports = value

    def encode_to_json(self, *args):
        """
        Makes out of the TestSequence a JSON object.
        """
        json_string = None
        json_string = json.dumps(self, default=self.serialize)
        return json_string

    def decode_from_json(self, json_data: dict):
        """
        Create a TestSpecification instance from a JSON object.
        """
        try:
            self.name = json_data['_name']
            self.description = json_data['_description']
            self.spec_version = json_data['_spec_version']
            self.iasw_version = json_data['_iasw_version']
            self.primary_counter_locked = json_data['_primary_counter_locked']
            self.precon_name = json_data['_precon_name']
            self.precon_code = json_data['_precon_code']
            self.precon_descr = json_data['_precon_descr']
            self.postcon_name = json_data['_postcon_name']
            self.postcon_code = json_data['_postcon_code']
            self.postcon_descr = json_data['_postcon_descr']
            self.comment = json_data['_comment']
            self.custom_imports = json_data['_custom_imports']
        except KeyError as keyerror:
            self.logger.error('KeyError: no {} could be found in the loaded data'.format(keyerror))

        self.sequences = []
        try:
            for index, seq in enumerate(json_data['sequences']):
                self.sequences.append(TestSequence(json_data=seq, logger=logger))
        except KeyError as keyerror:
            self.logger.error('KeyError: no {} could be found in the loaded data'.format(keyerror))
        return

    @staticmethod
    def serialize(obj):
        """
        JSON serializer for objects which are not serializable by default.
        Uses the overwritten __deepcopy__ methods of the classes, to make copies. Then takes the dictionarys of them
        and deletes the objects, which can not be serialized.
        """
        if isinstance(obj, TestSpecification):
            obj_copy = obj.__deepcopy__()
            obj_dict = obj_copy.__dict__
            del obj_dict['logger']
            return obj_dict
        if isinstance(obj, TestSequence):
            obj_copy = obj.__deepcopy__()
            obj_dict = obj_copy.__dict__
            del obj_dict['logger']
            return obj_dict
        if isinstance(obj, Step):
            obj_copy = obj.__deepcopy__()
            obj_dict = obj_copy.__dict__
            del obj_dict['test']
            del obj_dict['logger']
            return obj_dict

    def add_sequence(self):
        # find out the sequence number for the new one
        number_of_sequence = len(self.sequences)
        # append it to the list
        self.sequences.append(TestSequence(sequence=number_of_sequence, logger=logger))
        return number_of_sequence

    def get_sequence(self, sequence_number):
        for testseq in self.sequences:
            if testseq.sequence == sequence_number:
                return testseq


# @unittest.skip("demonstrating skipping")
class TestParseStepNumber(unittest.TestCase):
    """
    Test the function parse_step_number.
    """

    def test_datatype_str(self):
        # valid input
        self.assertEqual(parse_step_number('1'), (1, 0))
        self.assertEqual(parse_step_number('1.0'), (1, 0))
        self.assertEqual(parse_step_number('1.1'), (1, 1))
        self.assertEqual(parse_step_number('1.2'), (1, 2))

        # invalid input
        self.assertRaises(ValueError, parse_step_number, 'a')
        self.assertRaises(ValueError, parse_step_number, 'a.a')
        self.assertRaises(ValueError, parse_step_number, '1a.1')

    def test_datatype_int(self):
        self.assertEqual(parse_step_number(1), (1, 0))
        self.assertEqual(parse_step_number(2), (2, 0))

    def test_datatype_float(self):
        self.assertEqual(parse_step_number(1.0), (1, 0))
        self.assertEqual(parse_step_number(1.1), (1, 1))
        self.assertEqual(parse_step_number(1.2), (1, 2))

    def test_datatype_list(self):
        self.assertRaises(AssertionError, parse_step_number, [])


# @unittest.skip("demonstrating skipping")
class TestResortStepListByStepNumbers(unittest.TestCase):
    """
    Test the function resort_step_list_by_step_numbers. A method to verify the list consistency is implemented.
    """
    @classmethod
    def setUpClass(self):
        logger.debug('create a test specification and create step objects (not assigned to the test specification yet)')
        self.tstspc = TestSequence()
        self.step_1 = Step(step_num=1.0)
        self.step_1_1 = Step(step_num=1.1)
        self.step_1_2 = Step(step_num=1.2)
        self.step_2 = Step(step_num=2.0)
        self.step_3 = Step(step_num=3.0)
        self.step_4 = Step(step_num=4.0)
        self.step_4_1 = Step(step_num=4.1)
        self.step_5 = Step(step_num=5.0)
        self.step_6 = Step(step_num=6.0)
        self.step_6_1 = Step(step_num=6.1)
        self.step_6_2 = Step(step_num=6.2)
        self.step_6_3 = Step(step_num=6.3)
        self.step_7 = Step(step_num=7.0)

    def test_list_needs_sorting(self):
        logger.info('Running: {}'.format(self._testMethodName))
        self.tstspc.steps = [
            self.step_1,
            self.step_1_1,
            self.step_2,
            self.step_1_2,
            self.step_3,
            self.step_4,
            self.step_4_1,
            self.step_5,
            self.step_7,
            self.step_6,
            self.step_6_1,
            self.step_6_3,
            self.step_6_2,
        ]
        self.tstspc.log_list_of_steps()
        logger.debug('sorting the list')
        self.tstspc.resort_step_list_by_step_numbers()
        self.tstspc.log_list_of_steps()
        self.assertTrue(self.tstspc.verify_step_list_consistency())

    def test_nothing_to_sort(self):
        logger.info('Running: {}'.format(self._testMethodName))
        self.tstspc.steps = [
            self.step_1,
            self.step_1_1,
            self.step_1_2,
            self.step_2,
            self.step_3,
            self.step_4,
            self.step_4_1,
            self.step_5,
            self.step_6,
            self.step_6_1,
            self.step_6_2,
            self.step_6_3,
            self.step_7
        ]
        self.tstspc.log_list_of_steps()
        logger.debug('sorting the list')
        self.tstspc.resort_step_list_by_step_numbers()
        self.tstspc.log_list_of_steps()
        self.assertTrue(self.tstspc.verify_step_list_consistency())


# @unittest.skip("demonstrating skipping")
class TestAddStepBelow(unittest.TestCase):
    """
    Test if the function add_step_below does what it should.
    """

    def setUp(self) -> None:
        logger.info('setUp: {}'.format(self._testMethodName))
        logger.debug('create a test specification and add three steps')
        self.tstspc = TestSequence()
        logger.debug('Python object ID of the test specification: {}'.format(id(self.tstspc)))
        self.tstspc.log_list_of_steps()

        # create a new step and append it to the steps list
        number_new_step = create_step_number(1, 0)
        step_1 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_1)
        self.stp1 = id(step_1)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(2, 0)
        step_2 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_2)
        self.stp2 = id(step_2)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 0)
        step_3 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3)
        self.stp3 = id(step_3)

        self.tstspc.log_list_of_steps()

    def tearDown(self) -> None:
        logger.info('tearDown: after running test method: {}'.format(self._testMethodName))
        # save the test specification as JSON file
        json_file = os.path.join(confignator.get_option('logging', 'log-dir'), 'tst/data_model/' + self._testMethodName + '.json')
        with open(json_file, 'w') as fileobject:
            data = self.tstspc.encode_to_json()
            fileobject.write(data)
            logger.debug('Test specification was dumped as JSON: {}'.format(json_file))

    def test_add_step_below_unlocked(self):
        """
        The test specification is unlocked.
        add a step below step 2, the new step becomes (the new) step 3,
        the step which was number 3 till now, becomes step 4
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = False

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')

        # add the new step
        logger.info('going to add a step below Step 2.0')
        new_step = self.tstspc.add_step_below(2.0)
        nw_stp = id(new_step)

        self.tstspc.log_list_of_steps()

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '4.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[2]), nw_stp)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)

    def test_add_step_below_locked(self):
        """
        The test specification is locked.
        add a step below step 2, the new step becomes (the new) step 3,
        the step which was number 3 till now, becomes step 4
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = True

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')

        # add the new step
        logger.info('going to add a step below Step 2.0')
        new_step = self.tstspc.add_step_below(2.0)
        nw_stp = id(new_step)

        self.tstspc.log_list_of_steps()

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '2.1')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[2]), nw_stp)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)


# @unittest.skip("demonstrating skipping")
class TestAddStepAbove(unittest.TestCase):
    """
    Test if the function add_step_above does what it should.
    """

    def setUp(self) -> None:
        logger.info('setUp: {}'.format(self._testMethodName))
        logger.debug('create a test specification and add three steps')
        self.tstspc = TestSequence()
        logger.debug('Python object ID of the test specification: {}'.format(id(self.tstspc)))
        self.tstspc.log_list_of_steps()

        # create a new step and append it to the steps list
        number_new_step = create_step_number(1, 0)
        step_1 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_1)
        self.stp1 = id(step_1)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(2, 0)
        step_2 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_2)
        self.stp2 = id(step_2)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 0)
        step_3 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3)
        self.stp3 = id(step_3)

        self.tstspc.log_list_of_steps()

    def tearDown(self) -> None:
        logger.info('tear down after running test method: {}'.format(self._testMethodName))
        # save the test specification as JSON file
        json_file = os.path.join(confignator.get_option('logging', 'log-dir'), 'tst/data_model/' + self._testMethodName + '.json')
        with open(json_file, 'w') as fileobject:
            data = self.tstspc.encode_to_json()
            fileobject.write(data)
            logger.debug('Test specification was dumped as JSON: {}'.format(json_file))

    def test_add_step_above_unlocked(self):
        """
        The test specification is unlocked.
        add a step above step 2, the new step becomes (the new) step 2,
        the step which was number 2 till now, becomes step 3
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = False

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')

        # add the new step
        logger.info('going to add a step above Step 2.0')
        new_step = self.tstspc.add_step_above(2.0)
        nw_stp = id(new_step)

        self.tstspc.log_list_of_steps()

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '4.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), nw_stp)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)

    def test_add_step_above_locked(self):
        """
        The test specification is locked.
        add a step above step 2, the new step becomes (the new) step 1.1,
        the step which was number 2 till now, stays step 2
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = True

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')

        # add the new step
        logger.info('going to add a step above Step 2.0')
        new_step = self.tstspc.add_step_above(2.0)
        nw_stp = id(new_step)

        self.tstspc.log_list_of_steps()

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '1.1')
        self.assertEqual(self.tstspc.steps[2].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), nw_stp)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)


# @unittest.skip("demonstrating skipping")
class TestMoveStep(unittest.TestCase):
    """
    Test if moving of a step upwards or downwards works
    """

    def setUp(self) -> None:
        logger.info('setUp: {}'.format(self._testMethodName))
        logger.debug('create a test specification and add steps')
        self.tstspc = TestSequence()
        logger.debug('Python object ID of the test specification: {}'.format(id(self.tstspc)))
        self.tstspc.log_list_of_steps()

        # create a new step and append it to the steps list
        number_new_step = create_step_number(1, 0)
        step_1 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_1)
        self.stp1 = id(step_1)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(2, 0)
        step_2 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_2)
        self.stp2 = id(step_2)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 0)
        step_3 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3)
        self.stp3 = id(step_3)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 1)
        step_3_1 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_1)
        self.stp3_1 = id(step_3_1)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 2)
        step_3_2 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_2)
        self.stp3_2 = id(step_3_2)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 3)
        step_3_3 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_3)
        self.stp3_3 = id(step_3_3)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 4)
        step_3_4 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_4)
        self.stp3_4 = id(step_3_4)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 5)
        step_3_5 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_5)
        self.stp3_5 = id(step_3_5)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(4, 0)
        step_4 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_4)
        self.stp4 = id(step_4)

    def tearDown(self) -> None:
        logger.info('tearDown: after running test method: {}'.format(self._testMethodName))
        # save the test specification as JSON file
        json_file = os.path.join(confignator.get_option('logging', 'log-dir'), 'tst/data_model/' + self._testMethodName + '.json')
        with open(json_file, 'w') as fileobject:
            data = self.tstspc.encode_to_json()
            fileobject.write(data)
            logger.debug('Test specification was dumped as JSON: {}'.format(json_file))

    def test_move_step_to_top_unlocked(self):
        """
        It should not matter if the test is unlocked, if moving to the top.
        Move step 3.2 to the top.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = False

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        logger.info('moving step 3.2 to the top')
        step_to_move_index = self.tstspc.get_step_index('3.2')
        self.tstspc.move_step(step_to_move_index, 0)

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '4.0')
        self.assertEqual(self.tstspc.steps[4].step_number, '4.1')
        self.assertEqual(self.tstspc.steps[5].step_number, '4.2')
        self.assertEqual(self.tstspc.steps[6].step_number, '4.3')
        self.assertEqual(self.tstspc.steps[7].step_number, '4.4')
        self.assertEqual(self.tstspc.steps[8].step_number, '5.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp3_2)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)
        self.assertEqual(id(self.tstspc.steps[4]), self.stp3_1)
        self.assertEqual(id(self.tstspc.steps[5]), self.stp3_3)
        self.assertEqual(id(self.tstspc.steps[6]), self.stp3_4)
        self.assertEqual(id(self.tstspc.steps[7]), self.stp3_5)
        self.assertEqual(id(self.tstspc.steps[8]), self.stp4)

    def test_move_step_to_top_locked(self):
        """
        It should not matter if the test is unlocked, if moving to the top.
        Move step 3.2 to the top.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = True

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        logger.info('moving step 3.2 to the top')
        step_to_move_index = self.tstspc.get_step_index('3.2')
        self.tstspc.move_step(step_to_move_index, 0)

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '4.0')
        self.assertEqual(self.tstspc.steps[4].step_number, '4.1')
        self.assertEqual(self.tstspc.steps[5].step_number, '4.2')
        self.assertEqual(self.tstspc.steps[6].step_number, '4.3')
        self.assertEqual(self.tstspc.steps[7].step_number, '4.4')
        self.assertEqual(self.tstspc.steps[8].step_number, '5.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp3_2)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)
        self.assertEqual(id(self.tstspc.steps[4]), self.stp3_1)
        self.assertEqual(id(self.tstspc.steps[5]), self.stp3_3)
        self.assertEqual(id(self.tstspc.steps[6]), self.stp3_4)
        self.assertEqual(id(self.tstspc.steps[7]), self.stp3_5)
        self.assertEqual(id(self.tstspc.steps[8]), self.stp4)

    def test_move_step_upwards_unlocked(self):
        """
        Move step 3.2 to above step 3.0.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = False

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        logger.info('move step 3.2 to above step 3.0.')
        step_to_move_index = self.tstspc.get_step_index('3.2')
        self.tstspc.move_step(step_to_move_index, 2)

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '4.0')
        self.assertEqual(self.tstspc.steps[4].step_number, '4.1')
        self.assertEqual(self.tstspc.steps[5].step_number, '4.2')
        self.assertEqual(self.tstspc.steps[6].step_number, '4.3')
        self.assertEqual(self.tstspc.steps[7].step_number, '4.4')
        self.assertEqual(self.tstspc.steps[8].step_number, '5.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp3_2)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)
        self.assertEqual(id(self.tstspc.steps[4]), self.stp3_1)
        self.assertEqual(id(self.tstspc.steps[5]), self.stp3_3)
        self.assertEqual(id(self.tstspc.steps[6]), self.stp3_4)
        self.assertEqual(id(self.tstspc.steps[7]), self.stp3_5)
        self.assertEqual(id(self.tstspc.steps[8]), self.stp4)

    def test_move_step_upwards_locked(self):
        """
        Move step 3.2 to above step 3.0.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = True

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        logger.info('move step 3.2 to above step 3.0.')
        step_to_move_index = self.tstspc.get_step_index('3.2')
        self.tstspc.move_step(step_to_move_index, 2)

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '2.1')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp3_2)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3)
        self.assertEqual(id(self.tstspc.steps[4]), self.stp3_1)
        self.assertEqual(id(self.tstspc.steps[5]), self.stp3_3)
        self.assertEqual(id(self.tstspc.steps[6]), self.stp3_4)
        self.assertEqual(id(self.tstspc.steps[7]), self.stp3_5)
        self.assertEqual(id(self.tstspc.steps[8]), self.stp4)

    def test_move_step_downwards_unlocked(self):
        """
        Move step 3.2 to below step 4.0.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = False

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        logger.info('Move step 3.2 to below step 4.0.')
        step_to_move_index = self.tstspc.get_step_index('3.2')
        self.tstspc.move_step(step_to_move_index, 9)

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '4.0')
        self.assertEqual(self.tstspc.steps[8].step_number, '5.0')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp3)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3_1)
        self.assertEqual(id(self.tstspc.steps[4]), self.stp3_3)
        self.assertEqual(id(self.tstspc.steps[5]), self.stp3_4)
        self.assertEqual(id(self.tstspc.steps[6]), self.stp3_5)
        self.assertEqual(id(self.tstspc.steps[7]), self.stp4)
        self.assertEqual(id(self.tstspc.steps[8]), self.stp3_2)

    def test_move_step_downwards_locked(self):
        """
        Move step 3.2 to below step 4.0.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = True

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        logger.info('Move step 3.2 to below step 4.0.')
        step_to_move_index = self.tstspc.get_step_index('3.2')
        self.tstspc.move_step(step_to_move_index, 9)

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '4.0')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.1')

        # verify the order of the steps, by comparing the IDs of the Python objects
        self.assertEqual(id(self.tstspc.steps[0]), self.stp1)
        self.assertEqual(id(self.tstspc.steps[1]), self.stp2)
        self.assertEqual(id(self.tstspc.steps[2]), self.stp3)
        self.assertEqual(id(self.tstspc.steps[3]), self.stp3_1)
        self.assertEqual(id(self.tstspc.steps[4]), self.stp3_3)
        self.assertEqual(id(self.tstspc.steps[5]), self.stp3_4)
        self.assertEqual(id(self.tstspc.steps[6]), self.stp3_5)
        self.assertEqual(id(self.tstspc.steps[7]), self.stp4)
        self.assertEqual(id(self.tstspc.steps[8]), self.stp3_2)


# @unittest.skip("demonstrating skipping")
class TestRenumberSteps(unittest.TestCase):
    """
    Test if the method to renumber all steps works
    """

    def setUp(self) -> None:
        logger.info('setUp: {}'.format(self._testMethodName))
        logger.debug('create a test specification and add steps')
        self.tstspc = TestSequence()
        logger.debug('Python object ID of the test specification: {}'.format(id(self.tstspc)))

        # create a new step and append it to the steps list
        number_new_step = create_step_number(1, 0)
        step_1 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_1)
        self.stp1 = id(step_1)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(2, 0)
        step_2 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_2)
        self.stp2 = id(step_2)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 0)
        step_3 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3)
        self.stp3 = id(step_3)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 1)
        step_3_1 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_1)
        self.stp3_1 = id(step_3_1)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 2)
        step_3_2 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_2)
        self.stp3_2 = id(step_3_2)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 3)
        step_3_3 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_3)
        self.stp3_3 = id(step_3_3)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 4)
        step_3_4 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_4)
        self.stp3_4 = id(step_3_4)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(3, 5)
        step_3_5 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_3_5)
        self.stp3_5 = id(step_3_5)

        # create a new step and append it to the steps list
        number_new_step = create_step_number(4, 0)
        step_4 = Step(step_num=number_new_step, test_seq=self.tstspc)
        self.tstspc.steps.append(step_4)
        self.stp4 = id(step_4)

    def tearDown(self) -> None:
        logger.info('tearDown: after running test method: {}'.format(self._testMethodName))
        # save the test specification as JSON file
        json_file = os.path.join(confignator.get_option('logging', 'log-dir'), 'tst/data_model/' + self._testMethodName + '.json')
        with open(json_file, 'w') as fileobject:
            data = self.tstspc.encode_to_json()
            fileobject.write(data)
            logger.debug('Test specification was dumped as JSON: {}'.format(json_file))

    def test_move_step_to_top_unlocked(self):
        """
        It should not matter if the test is unlocked, if moving to the top.
        Move step 3.2 to the top.
        """
        logger.info('Running {}'.format(self._testMethodName))
        self.tstspc.primary_counter_locked = False

        # verify the numeration of the steps before adding a new step
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '3.1')
        self.assertEqual(self.tstspc.steps[4].step_number, '3.2')
        self.assertEqual(self.tstspc.steps[5].step_number, '3.3')
        self.assertEqual(self.tstspc.steps[6].step_number, '3.4')
        self.assertEqual(self.tstspc.steps[7].step_number, '3.5')
        self.assertEqual(self.tstspc.steps[8].step_number, '4.0')

        # renumber the steps
        logger.info('renumber the steps')
        self.tstspc.renumber_steps()

        # verify the numeration of the steps
        self.assertEqual(self.tstspc.steps[0].step_number, '1.0')
        self.assertEqual(self.tstspc.steps[1].step_number, '2.0')
        self.assertEqual(self.tstspc.steps[2].step_number, '3.0')
        self.assertEqual(self.tstspc.steps[3].step_number, '4.0')
        self.assertEqual(self.tstspc.steps[4].step_number, '5.0')
        self.assertEqual(self.tstspc.steps[5].step_number, '6.0')
        self.assertEqual(self.tstspc.steps[6].step_number, '7.0')
        self.assertEqual(self.tstspc.steps[7].step_number, '8.0')
        self.assertEqual(self.tstspc.steps[8].step_number, '9.0')


def create_start_sequence_step(seq_to_start: int) -> Step:
    """
    Creates a Step instance which has the purpose to be the starting point of a sequence.

    :param: int seq_to_start: the number of the sequence which should be started.
    """
    assert isinstance(seq_to_start, int)
    s = Step()
    s.start_sequence = seq_to_start
    s.description = _('Start sequence {}'.format(seq_to_start))
    s.command_code = '#ToDo'
    return s


def create_stop_sequence_step(seq_to_stop: int) -> Step:
    """
    Creates a Step instance which has the purpose to trigger the stop of a sequence.

    :param: int seq_to_stop: the number of the sequence which should be stopped.
    """
    assert isinstance(seq_to_stop, int)
    s = Step()
    s.start_sequence = seq_to_stop
    s.description = _('Stop sequence {}'.format(seq_to_stop))
    s.command_code = '#ToDo'
    return s


if __name__ == '__main__':
    # create a log file for the self testing
    log_path = confignator.get_option('logging', 'log-dir')
    log_file = os.path.join(log_path, 'tst/data_model/data_model.log')
    logger.addHandler(hdlr=console_hdlr)
    file_hdlr = toolbox.create_file_handler(file=log_file)
    logger.addHandler(hdlr=file_hdlr)

    test_program = unittest.main(verbosity=2, exit=False)
    logger.info('Ran {} tests'.format(test_program.result.testsRun))
    if test_program.result.wasSuccessful():
        logger.info('Self-test program was successful.')
    else:
        logger.critical('Self-test program failed.')
    if len(test_program.result.failures) > 0:
        logger.error('{} tests failed'.format(len(test_program.result.failures)))
    for fail in test_program.result.failures:
        logger.error(fail[0])
        logger.debug(fail[1])
