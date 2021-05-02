"""
Currently these use cases are considered:

    * read only: retrieve a option from any configfile in a one-liner (for example to get a path)

        * cfg = confignator.get_config() -> loads big-merger-config
        * opt = confignator.get_option() -> gives the value of the option after loading the big-merger-config

            * file crossing interpolation of option values
            * always loads the files
            * no need to specify the file where the option is located

        * opt = confignator.get_bool_option() -> same as get_option, but the option is parsed as boolean (False, false, 0 => False)

    * manipulate the configuration, use it and save it (e.g.: a application loads it's own configuration file)

        * cfg = confignator.get_config(file_path=<filepath>) -> loads only the specified configuration file

            * instance cfg: no reloading after changing a section/option
            * cfg.save_to_file(): saves the configuration as file
            * cfg: all methods and attributes of the super class configparser.Parser are available

    * changing and save a existing option, without loading a specified configuration file prior

        * confignator.save_option()

            * -> loads the big-merger-config
            * -> looks, in which file the option occurs (the [section][option] needs to be unique)
            * -> only if one occurrence, this file is loaded in single mode, the option set and this config saved

"""
import logging
import sys
import unittest
import configparser
import confignator

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

fmt = ''
fmt += '%(levelname)s\t'
# fmt += '%(asctime)s\t'
fmt += '%(message)s\t'
# fmt += '%(name)s\t'
fmt += '%(funcName)s\t'
# fmt += '%(lineno)s\t'
# fmt += '%(filename)s\t'
# fmt += '%(module)s\t'
# fmt += '%(pathname)s\t'
# fmt += '%(process)s\t'
# fmt += '%(processName)s\t'
# fmt += '%(thread)s\t'
# fmt += '%(threadName)s\t'


def create_console_handler(frmt: str = fmt, hdlr_lvl: int = logging.WARNING):
    """
    Creates a StreamHandler which logs to the console.
    :param str frmt: Format string for the log messages
    :param hdlr_lvl: Level of the handler
    :return: Returns the created handler
    :rtype: logging.StreamHandler
    """
    hdlr = logging.StreamHandler(stream=sys.stdout)
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(hdlr_lvl)
    return hdlr


console_hdlr = create_console_handler(frmt=fmt, hdlr_lvl=logging.DEBUG)
logger.addHandler(hdlr=console_hdlr)


class TestGetConfigWithoutFilename(unittest.TestCase):
    """
    Using the confignator.get_config() without passing the argument *file_path*,
    should return the 'big merge' configuration.
    This merge includes the files confignator.cfg, and the basic egse.cfg.
    All files listed in the section 'config-files' are loaded too.
    The returned instance sadly, can not hold the information from which file a option was loaded.
    """
    cfg = confignator.get_config()

    logger.info('loaded files:')
    for f in cfg.files:
        logger.info('   {}'.format(f))
    logger.info('loaded sections:')
    logger.info(cfg.sections())

    def test_without_filename(self):
        self.assertTrue(isinstance(self.cfg, configparser.ConfigParser))

    def test_number_of_loaded_files(self):
        number_of_files = len(self.cfg.files)
        self.assertGreater(number_of_files, 1)


class TestGetOption(unittest.TestCase):

    def test_option_exist(self):
        self.assertTrue(isinstance(confignator.get_option('paths', 'ccs'), str))

    def test_option_does_not_exist(self):
        self.assertFalse(isinstance(confignator.get_option('paths', 'hudriwudi'), str))


class TestSaveOption(unittest.TestCase):
    logger.info('testing the save_option')
    opt_before = confignator.get_option('paths', 'ccs')

    def tearDown(self) -> None:
        confignator.save_option(section='paths', option='ccs', value=self.opt_before, logger=logger)

    def test_change_in_file(self, logger=logger):
        new_value = self.opt_before + '/unittest'
        confignator.save_option(section='paths', option='ccs', value=new_value, logger=logger)
        opt_after = confignator.get_option('paths', 'ccs')
        self.assertEqual(opt_after, new_value)

    def test_invalid_new_value_restore_old_value(self):
        """
        This should show, that a invalid interpolation, does not destroy the config handling.
        It should always be possible, even if the interpolation fails, to restore the old value.
        """
        invalid_new_value = '${notExisting:interpolation}/myNewPath'
        confignator.save_option(section='paths', option='ccs', value=invalid_new_value, logger=logger)
        confignator.save_option(section='paths', option='ccs', value=self.opt_before, logger=logger)
        opt_after = confignator.get_option('paths', 'ccs')
        self.assertEqual(opt_after, self.opt_before)


class TestModuleGetConfigWithFilename(unittest.TestCase):
    """
    Using the confignator.get_config(file_path='<filepath>') passing the argument *file_path*,
    should return a instance where only this file is loaded.
    Thus all manipulations can easily be saved in the file.
    All methods and attributes of the super class configparser.Parser are available.
    """
    path_cfg = confignator.get_option('config-files', 'ccs')
    cfg = confignator.get_config(file_path=path_cfg)

    logger.info('loaded files:')
    for f in cfg.files:
        logger.info('   {}'.format(f))
    logger.info('loaded sections:')
    logger.info(cfg.sections())

    def test_without_filename(self):
        self.assertTrue(isinstance(self.cfg, configparser.ConfigParser))

    def test_number_of_loaded_files(self):
        number_of_files = len(self.cfg.files)
        self.assertEqual(number_of_files, 1)


if __name__ == '__main__':
    unittest.main()
