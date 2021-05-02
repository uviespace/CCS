"""
Configure logging
=================
"""
import logging
import logging.config
import os
import datetime

from . import tools


cmd_log_auxiliary = '_command.log'
vrc_log_auxiliary = '_verification.log'
man_log_auxiliary = '_manually.log'


def get_path_for_logs(module_name):
    """
    The path were the log files are saved is built out of the module name and the path which was specified in egse.cfg
    :param str module_name: this is the name of the logfile
    :return: absolute path were the logfile is saved
    :rtype: str
    """
    # ToDo create the filename using the testing_logger.cmd_scrpt_auxiliary variable
    cfg = tools.read_config()
    # Fetch the path from the project config file
    path = cfg.get('LOGGING', 'test_run')
    # Create the directory for the logging files
    os.makedirs(path, mode=0o777, exist_ok=True)
    filename = path + module_name + '.log'
    return filename


def strip_parent_package(text):
    """
    Strips all text before the test name. Strips python package access syntax.
    Since the test script were moved into folders, the __name__ variable of a test has this attribute access syntax.
    For example: IASW.IASW_1_DB is changed to IASW_1_DB.

    :param text: str
        Name of the file

    :return: str
        Name of the test.
    """
    assert isinstance(text, str)
    while True:
        dot = text.find('.')
        if dot == -1:
            break
        after = text[dot + 1:]
        text = after
    return text


date_time_format = '%Y-%m-%d %H:%M:%S,%f'


def extract_date(line):
    """
    Extracts the date and time of a line of the log file
    :param str line: line of a log file
    :return: datetime object of the parsed date and time
    :rtype: datetime.datetime
    """
    start = line.find('\t') + 1
    end = line.find('\t', start)
    date_str = line[start:end]
    date = datetime.datetime.strptime(date_str, date_time_format)
    return date


def my_formatter():
    return logging.Formatter(fmt='%(levelname)s\t%(asctime)s\tlogger: %(name)s:\t%(message)s')


def cmd_log_handler(file_name):
    name = 'cmd_log_hdlr'
    # removing the verification log handler if it exists
    for hdlr in logging.root.handlers:
        if hdlr.get_name() == 'ver_log_hdlr':
            logging.root.removeHandler(hdlr)
    # create and add the handler for the command script
    if not handler_exists(handler_name=name):
        path_cmd_log = get_path_for_logs(file_name)
        new_handler = logging.FileHandler(path_cmd_log, mode='a', encoding=None, delay=False)
        new_handler.set_name(name)
        new_handler.setFormatter(my_formatter())
        logging.root.addHandler(new_handler)
    else:
        path_cmd_log = handler_file_path(handler_name=name)

    return path_cmd_log


def ver_log_handler(file_name):
    # removing the command log handler if it exists
    name = 'ver_log_hdlr'
    for hdlr in logging.root.handlers:
        if hdlr.get_name() == 'cmd_log_hdlr':
            logging.root.removeHandler(hdlr)
    # create and add the handler for the verification
    if not handler_exists(name):
        path_ver_log = get_path_for_logs(file_name)
        new_handler = logging.FileHandler(path_ver_log, mode='a', encoding=None, delay=False)
        new_handler.set_name(name)
        new_handler.setFormatter(my_formatter())
        logging.root.addHandler(new_handler)


# def create_console_handler():
#     name = 'console'
#     if not handler_exists(name):
#         new_handler = logging.StreamHandler(stream=sys.stdout)
#         new_handler.set_name(name)
#         new_handler.setLevel(logging.DEBUG)
#         new_handler.setFormatter(my_formatter())
#         logging.root.addHandler(new_handler)


def handler_exists(handler_name):
    for hdlr in logging.root.handlers:
        if hdlr.get_name() == handler_name:
            return True


def handler_file_path(handler_name):
    for hdlr in logging.root.handlers:
        if hdlr.get_name() == handler_name:
            return hdlr.baseFilename


def setup_logging(log_file_name=None, level=logging.INFO):
    """
    the function setup_logging uses a dictionary based configuration to deploy loggers from the python module logging.
    The configuration is a python dictionary and should be passed to logging.config.dictConfig().
    If logger are defined with the name argument __name__ the handlers of 'root' are used.
    Every integration test should call the setup_logging function in order to change the logfile name. Thus every test
    creates its own file. For use in modules just the following lines are needed:
    import logging.config
    import config_logging
    config_logging.setup_logging(log_file_name=__name__, level='DEBUG')  # -> this achieves that a new file generated
    logger = logging.getLogger(__name__)  # -> this sets which logger is used

    :param str log_file_name: name of the file where the log is saved
    :param level: log level of the logging module
    """
    # if log_file_name is not None:
    #     file_name = strip_parent_package(text=log_file_name)
    #     path = get_path_for_logs(file_name)
    #     path_run_tests = get_path_for_logs('summary')
    #     path_all_in_one = get_path_for_logs('all')
    #     path_cmd_log = get_path_for_logs(file_name + '_cmd')
    #     path_ver_log = get_path_for_logs(file_name + '_ver')

    path = log_file_name

    # configuration dictionary:
    config = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'standard': {
                'format': '%(levelname)s\t%(asctime)s\tlogger: %(name)s:\t%(message)s'
            },
            'format_1': {
                'format': '%(levelname)s\t%(name)s:  %(message)s'
            },
            'w_threads': {
                'format': '%(relativeCreated)6d %(threadName)s %(levelname)s\t%(name)s:  %(message)s'
            },
            'simple': {
                'format': '%(levelname)s\t%(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG',
                'formatter': 'format_1',
                'stream': 'ext://sys.stdout'
            },
            # 'file': {
            #     'class': 'logging.FileHandler',
            #     'level': 'DEBUG',
            #     'formatter': 'standard',
            #     'filename': path_all_in_one,
            #     'mode': 'a'
            # },
            # 'allinone': {
            #     'class': 'logging.FileHandler',
            #     'level': 'DEBUG',
            #     'formatter': 'standard',
            #     'filename': path_all_in_one,
            #     'mode': 'a'
            # },
            # 'file_run_tests': {
            #     'class': 'logging.FileHandler',
            #     'level': 'DEBUG',
            #     'formatter': 'simple',
            #     'filename': path_run_tests,
            #     'mode': 'a'
            # },
            'to_file': {
                'class': 'logging.FileHandler',
                'level': 'DEBUG',
                'formatter': 'standard',
                'filename': path,
                'mode': 'a'
            },
            # 'command_log_file': {
            #     'class': 'logging.FileHandler',
            #     'level': 'DEBUG',
            #     'formatter': 'standard',
            #     'filename': path_cmd_log,
            #     'mode': 'a'
            # },
            # 'verification_log_file': {
            #     'class': 'logging.FileHandler',
            #     'level': 'DEBUG',
            #     'formatter': 'standard',
            #     'filename': path_ver_log,
            #     'mode': 'a'
            # }
        },
        'loggers': {
            'tst_main': {
                'level': 'DEBUG',
                'handlers': ['to_file'],
                'propagate': False
            },
            # 'run_tests': {
            #     'level': 'DEBUG',
            #     'handlers': ['console', 'file_run_tests'],
            #     'propagate': False
            # },
            # 'steps_manually': {
            #     'level': 'DEBUG',
            #     'handlers': ['console', 'file_for_steps_manually'],
            #     'propagate': False
            # },
            # 'command_log': {
            #     'level': 'DEBUG',
            #     'handlers': ['console', 'command_log_file'],
            #     'propagate': True
            # }
        },
        'root': {
            'level': level,
            'handlers': ['console', 'to_file']
        }
    }
    # Load the configuration
    logging.config.dictConfig(config)


# if __name__ == '__main__':
#     setup_logging(log_file_name=__name__, level=logging.INFO)
#     logger = logging.getLogger(__name__)
#     logger.info('The logger was set up successfully.')
