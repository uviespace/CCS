#!/usr/bin/env python3
"""
The confignator is a derived class of the configparser.Configparser. Some methods were added:

* loading of all configuration files, which are listed in the base configuration file
* testing of the interpolation of all options
* saving the current configuration to a file
* some methods for the GUI (to edit a config file)

This module also has following functions, which should make the use of configuration file easy.

* get_config: when no file_path is provided it loads the default configuration
* get_option: it retrieves a option. If a file_path is given, this config file is used.
* get_bool_option: it retrieves a option as boolean. If a file_path is given, this config file is used.
* save_option: loads the big-merger, looks for the origin of the option and saves it there.

The confignator package is designed to be installed as pip3 module.
It is important, that the installation is evoked from the directory, where the base configuration file is located, because
this path will be set as the default path. Hence, when using the default config file, no file_path needs to be provided.

Configuration files should use INI syntax.

Module content:

* Module level functions:

    * :func:`create_console_handler <confignator.config.create_console_handler>`
    * :func:`build_log_file_path <confignator.config.build_log_file_path>`
    * :func:`create_file_handler <confignator.config.create_file_handler>`
    * :func:`get_config <confignator.config.get_config>`
    * :func:`get_option <confignator.config.get_option>`
    * :func:`get_bool_option <confignator.config.get_bool_option>`
    * :func:`save_option <confignator.config.save_option>`

* Classes:

    * :class:`configparser.ConfigParser: Config <confignator.config.Config>`
"""
import configparser
import os
import logging
import logging.handlers

cfg = configparser.ConfigParser()
confignator_cfg = os.path.join(os.path.dirname(__file__), 'confignator.cfg')
cfg.read(confignator_cfg)
basic_config = cfg.get('confignator-paths', 'basic-cfg')
docu = cfg.get('confignator-paths', 'docu')

config_files_section = 'config-files'


# ------------------------------- logging ------------------------------------------------------------
fmt = ''
fmt += '%(levelname)s\t'
fmt += '%(asctime)s\t'
fmt += '%(message)s\t'
fmt += '%(name)s\t'
fmt += '%(funcName)s\t'
fmt += '%(lineno)s\t'
fmt += '%(filename)s\t'
fmt += '%(module)s\t'
fmt += '%(pathname)s\t'
fmt += '%(process)s\t'
fmt += '%(processName)s\t'
fmt += '%(thread)s\t'
fmt += '%(threadName)s\t'

logging_format = fmt
logging_level_file = logging.INFO
logging_level_console = logging.WARNING
module_logger = logging.getLogger(__name__)
# module_logger.setLevel(logging.INFO)
module_logger.setLevel(getattr(logging, cfg.get('confignator-logging', 'level')))
logging_file_name = 'confignator.log'


def set_own_log_file_path():
    """
    The log file of the confignator is in its installation folder.
    This function should set this path in the configuration file of the confignator.
    """
    log_file_path = os.path.join(os.path.dirname(__file__), logging_file_name)
    own_cfg = get_config(confignator_cfg, logger=module_logger)
    own_cfg.save_option_to_file(section='confignator-paths', option='log-file', value=log_file_path)
    return


def create_console_handler(frmt=logging_format):
    """
    Creates a StreamHandler which logs to the console.

    :param str frmt: Format string for the log messages
    :return: Returns the created handler
    :rtype: logging.StreamHandler
    """
    hdlr = logging.StreamHandler()
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(logging_level_console)
    return hdlr


console_hdlr = create_console_handler()
module_logger.addHandler(hdlr=console_hdlr)


def build_log_file_path():
    """"
    The path for the log file is build using the location of this file (__file__).

    :return: absolute path to the logging file
    :rtype: str
    """
    file_path = os.path.join(os.path.dirname(__file__), logging_file_name)
    try:
        os.makedirs(os.path.dirname(file_path), mode=0o777, exist_ok=True)
    except TypeError as e:
        module_logger.exception(e)
        module_logger.critical("Could not create directory for the logging file.")
    return file_path


def create_file_handler(frmt=logging_format):
    """
    Creates a RotatingFileHandler

    :param str frmt: Format string for the log messages
    :return: Returns the created handler
    :rtype: logging.handlers.RotatingFileHandler
    """
    file_name = build_log_file_path()
    hdlr = logging.handlers.RotatingFileHandler(filename=file_name, mode='a', maxBytes=300000, backupCount=0)
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(logging_level_file)
    return hdlr


file_hdlr = create_file_handler()
module_logger.addHandler(hdlr=file_hdlr)
# ---------------------------------------------------------------------------------------------------


def get_config(file_path: str = None, logger: logging.Logger = module_logger, load_basic_files: bool = None,
               load_denoted_files: bool = None, check_interpolation: bool = True):
    """
    Two use cases:

        * a file_path is passed: only this configuration file will be in the returned instance
        * file_path is None: the confignator, the basic and all denoted files are loaded -> big merge

    Note: If no file_path is given, the hardcoded path is used. This hardcoded path is created at the installation of the
    confignator package and is the path where the installation was started.

    :param str, list file_path: path to a configuration file
    :param logging.Logger logger: Logger passed as function argument
    :param bool load_basic_files: can be used to force to load the basic configuration files (confignator.cfg, egse.cfg)
    :param bool load_denoted_files: can be used to force to load the files listed in the section for config-files
    :param bool check_interpolation: toggle checking of correct value interpolation
    :return: the parsed configuration
    :rtype: configparser.Config
    """
    # the two use cases
    if file_path is None:
        load_basic = True
        load_denoted = True
    else:
        load_basic = False
        load_denoted = False
    # force to load basic and or denoted configuration files
    if load_basic_files is not None:
        load_basic = load_basic_files
    if load_denoted_files is not None:
        load_denoted = load_denoted_files

    try:
        config = Config(file_path=file_path, logger=logger, load_basic_files=load_basic, load_denoted_files=load_denoted,
                        check_interpolation=check_interpolation)
    except Exception as exception:
        config = None
        logger.error('could not read the configuration file: {}'.format(file_path))
        logger.exception(exception)
    return config


def get_option(section: str, option: str, logger: logging.Logger = module_logger) -> str:
    """
    This function can be used to quickly retrieve an option from a configuration file. If file_path is not provided, the
    hardcoded path in this module (path) is used.

    :param str section: section in the configuration file
    :param str option: entry in the section
    :param logging.Logger logger: Logger passed as function argument
    :return: the value of the entry
    :rtype: str
    """
    try:
        config = get_config(logger=logger, check_interpolation=False)
        return config.get(section, option)
    except KeyError:
        logger.error('Confguration has no section {}'.format(section))
    except configparser.NoOptionError:
        logger.error('Confguration has no option {}'.format(option))
    except configparser.InterpolationError:
        logger.error('failed to retrieve entry {} from section {}'.format(option, section))
    except AttributeError as ae:
        logger.error('The configuration could not be loaded, thus getting the option failed.')
        logger.exception(ae)
    except Exception as e:
        logger.error('failed to retrieve entry {} from section {}'.format(option, section))
        logger.exception(e)


def get_bool_option(section: str, option: str, logger: logging.Logger = module_logger) -> bool:
    """
    This function can be used to quickly retrieve an option from a configuration file. If file_path is not provided, the
    hardcoded path in this module (path) is used.

    :param str section: section in the configuration file
    :param str option: entry in the section
    :param logging.Logger logger: Logger passed as function argument
    :return: the value of the entry
    :rtype: bool
    """
    try:
        config = get_config(logger=logger)
        return config.getboolean(section, option)
    except KeyError:
        logger.error('Confguration has no section {}'.format(section))
    except configparser.NoOptionError:
        logger.error('Confguration has no option {}'.format(option))
    except configparser.InterpolationError:
        logger.error('Confguration has no option {}'.format(option))
    except AttributeError as ae:
        logger.error('The configuration could not be loaded, thus getting the option failed.')
        logger.exception(ae)
    except Exception as e:
        logger.error('failed to retrieve entry {} from section {}'.format(option, section))
        logger.exception(e)


def save_option(section: str, option: str, value: str, logger: logging.Logger = module_logger):
    """
    Writes a option into the file, where it was loaded. If no file_path is provided the config with is loaded by default
    is used. The section and option has to be unique. If more config files are loaded and merged and two or more have
    same section and option, saving is not possible.
    Loads the configuration, then sets the option and saves it again as file.

    :param str section: section name (case sensitive)
    :param str option: option name (case insensitive)
    :param str value: value which should be saved
    :param logging.Logger logger: if no logger is provided, the module level logger is used (config.py)
    """
    cfg = get_config(logger=logger)
    if cfg is not None:
        cfg.save_option_to_file(section=section, option=option, value=value)
    else:
        logger.error('Could not load the configuration. Saving of the option was not possible.')


class Config(configparser.ConfigParser):

    def __init__(self, file_path, logger=module_logger, load_basic_files=True, load_denoted_files=True,
                 check_interpolation=True, *args, **kwargs):
        """
        Init function of the derived ConfigParser class. If a file_path is provided, all configuration files are loaded.
        Does one or more of these files have a section 'config-files' all listed files are loaded too.

        :param str, list file_path: paths to config files
        :param logging.Logger logger: A logger can be
        :param bool load_sect_cfg_files: if set to True, only the file provided in file_path will be loaded
        """
        super().__init__(interpolation=configparser.ExtendedInterpolation(), *args, **kwargs)
        self.logger = logger
        self.logger.debug('provided file_path: {}'.format(file_path))
        self._load_denoted_files = None
        self.load_denoted_files = load_denoted_files
        self._load_basic_files = None
        self.load_basic_files = load_basic_files
        self.files = []  # should always be a list of successful loaded files

        if load_basic_files is True:
            self.load_config_file(confignator_cfg)
            self.load_config_file(basic_config)

        if isinstance(file_path, str):
            self.load_config_file(file_path)
        elif isinstance(file_path, list):
            for item in file_path:
                self.load_config_file(item)

        if load_denoted_files is True:
            # load all configuration files in the section config_files_section
            self.load_config_files_section()

        # test all interpolations in the values
        if check_interpolation:
            self.test_all_options()

    @property
    def load_denoted_files(self):
        return self._load_denoted_files

    @load_denoted_files.setter
    def load_denoted_files(self, value):
        assert isinstance(value, bool)
        self._load_denoted_files = value

    @property
    def load_basic_files(self):
        return self._load_denoted_files

    @load_basic_files.setter
    def load_basic_files(self, value):
        assert isinstance(value, bool)
        self._load_basic_files = value

    def load_config_file(self, file_path):
        """
        Loading of the file in file_path into the current instance.

        :param file_path:
        :return:
        """
        if file_path is None:
            raise ValueError(file_path)
        try:
            with open(file_path, 'r') as fi:
                self.read_file(fi)
            if file_path not in self.files:
                # add a entry in the file list, if it is not there
                self.files.append(file_path)
            self.logger.debug('read config file: {}'.format(file_path))
        except FileNotFoundError:
            if file_path in self.files:
                # delete the entry from the file list, because loading failed
                file_path_idx = self.files.index(file_path)
                self.files.pop(file_path_idx)
            self.logger.critical('failed to read config file: "{}"'.format(file_path))

    def load_config_files_section(self):
        """
        Every option in the section config_files_section will be treated as path to a configuration file. Using the
        function ConfigParser.read_file, every configuration file will be read and added to the current ConfigParser
        instance. If two config files have exactly the same section and option, the option of the file loaded at last
        will overwrite the value.
        """
        if self.has_section(config_files_section):
            for opt in self.options(config_files_section):
                try:
                    path = os.path.abspath(self.get(config_files_section, opt))
                    self.load_config_file(path)
                except configparser.InterpolationError:
                    self.logger.warning('failed to load configfile because interpolation of option {} in section {} failed'.format(opt, config_files_section))
        else:
            self.logger.debug('no section {} found'.format(config_files_section))

    def test_all_options(self, ignore_failures: bool = False) -> bool:
        """
        All options are tested, if the interpolation is working.

        :return: True if all interpolations could be evaluated. False if one interpolation fails.
        :rtype: bool
        """
        failed = False
        for s in self.sections():
            for o in self.options(s):
                try:
                    self.get(s, o)
                except configparser.InterpolationError:
                    if ignore_failures is False:
                        self.logger.debug('failed interpolation of the option [{}][{}]'.format(s, o))
                    failed = True
        if failed is True:
            self.logger.warning('interpolation of options FAILED')
        if failed is False:
            self.logger.debug('interpolation of options was SUCCESSFUL')
        return failed

    def set_parameter(self, section, option, value):
        """
        Changes a parameter in the configuration file. Checks if there is a interpolation syntax in the old value.
        If this is the case, the interpolation syntax is taken over for the new value.

        :param section: the section in the configuration file
        :param option: the option is the parameter within the section
        :param value: the new value of the parameter
        """
        # check if a interpolation syntax exists in the old value and take over into the new value
        raw_value_before = self.get(section, option, raw=True)
        found = raw_value_before.find('${')
        if found != -1:
            try:
                closing_bracket = raw_value_before.find('}')
                inter_syntax = raw_value_before[found:closing_bracket+1]
                remaining_value = raw_value_before[closing_bracket+1:]

                merge_config = get_config()
                interpolated_option = merge_config.get(section, option, raw=False)
                end = interpolated_option.find(remaining_value)
                dissolved_inter_syntax = interpolated_option[:end]
                if value.find(dissolved_inter_syntax) != -1:
                    value = value.replace(dissolved_inter_syntax, inter_syntax)
            except:
                self.logger.warning('failed to overtake the interpolation expression')
        self.set(section=section, option=option, value=value)

    def save_option_to_file(self, section: str, option: str, value: str):
        """
        Finds the configuration file where the option originated from. Load this configuration. Set the new value of
        the option and save it.

        :param str section: section name (case sensitive)
        :param str option: option name (case insensitive)
        :param str value: value which should be saved
        """
        # find the file where the section/option is from
        occurrence = []
        for file in self.files:
            tempcfg = get_config(file_path=file, load_basic_files=False, load_denoted_files=False, check_interpolation=False)
            found = tempcfg.has_section(section=section)
            if found is True:
                occurrence.append(file)
        if len(occurrence) == 0:
            self.logger.error('No configuration files with section [{}] found. Saving not possible.'.format(section))
            # self.logger.error('should it be saved as a new section & option?')
        elif len(occurrence) > 1:
            self.logger.error('Found section [{}] in more than one configuration file. Saving not possible. Occurrences in: {}'.format(section, occurrence))
        elif len(occurrence) == 1:
            # load the config (only the specified file, no other)
            tempcfg = get_config(file_path=occurrence[0], load_basic_files=False, load_denoted_files=False, check_interpolation=False)
            # set the option
            tempcfg.set(section=section, option=option, value=value)
            # check if this entry has valid interpolations
            # try:
            #     get_option(section=section, option=option)  # here the merged default config is used
            # except configparser.InterpolationError:
            #     self.logger.error('The interpolation of the option [{}][{}] with the value [{}] failed.'.format(section, option, value))
            # save the config
            tempcfg.save_to_file()
        self.reload_config_files()

    def remove_option_from_file(self, section: str, option: str):
        # find the file where the option is from
        occurrence = []
        for file in self.files:
            tempcfg = get_config(file_path=file, load_basic_files=False, load_denoted_files=False,
                                 check_interpolation=False)
            found = tempcfg.has_option(section=section, option=option)
            if found is True:
                occurrence.append(file)
        if len(occurrence) == 0:
            self.logger.warning('No configuration files with the entry [{}[{}] found'.format(section, option))
        else:
            if len(occurrence) > 1:
                self.logger.warning('Found the entry [{}][{}] in more than one configuration file: {}'.format(section, option, occurrence))
            for occ in occurrence:
                tempcfg = get_config(file_path=occ, load_basic_files=False, load_denoted_files=False, check_interpolation=False)
                tempcfg.remove_option(section, option)
                tempcfg.save_to_file()
        self.reload_config_files()

    def save_to_file(self, file_path: str = None) -> str:
        """
        Saves the current configuration in a file. If no file_path is provided the file_path of the config is used.

        :param file_path: path to the file where the configuration will be saved
        :return: list of file paths and a message
        :rtype: tuple (list, str)
        """
        if file_path is None:
            if len(self.files) == 1:
                file_path = self.files[0]
            else:
                message = 'No file_path was provided. The config is a merge. Which file should be used for saving?'
                raise ValueError(message)

        file_path = os.path.abspath(file_path)

        with open(file_path, 'w') as configfile:
            if len(self.files) > 1:
                configfile.write('# This configuration is a merge from following files:\n')
                for k in self.files:
                    configfile.write('#    {}\n'.format(k))
                configfile.write('\n')
                self.logger.info('A merged config was written to {}.'.format(file_path))
            self.write(configfile)
        self.logger.debug('Successfully saved the configuration in the file {}'.format(file_path))

        return file_path

    def open_file(self, file_path):
        """
        Loading the configuration from the file found in file_path into the current ConfigParser instance.

        :param str file_path: path to a configuration file in INI style
        """
        with open(file_path, 'r') as fi:
            self.read_file(fi)
        fi.close()
        self.files.append(file_path)

    def reload_config_files(self):
        """
        Deletes all sections and loads all configuration files in self.files
        """
        for sec in self.sections():
            self.remove_section(sec)
        for f in self.files:
            self.load_config_file(f)
        if self.load_denoted_files is True:
            self.load_config_files_section()
        if self.load_basic_files is True:
            self.load_config_file(confignator_cfg)
            self.load_config_file(basic_config)
