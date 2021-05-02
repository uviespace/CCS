import os
import sys
import logging
import logging.handlers


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


def extract_descriptions(frmt: str = fmt) -> list:
    """
    Extract the names/descriptions of the entries in a format string for the logging module.
    In a nutshell: get a list of the entry names without special characters.
    The separator of the entries must be a tab.
    :param frmt:
    :return:
    """
    names = []
    start_idx = 0
    left = '%('
    right = ')s\t'
    while frmt.find(left, start_idx) != -1:
        left_idx = frmt.find(left, start_idx)
        end_idx = frmt.find(right, start_idx)
        if end_idx != -1:
            entry = frmt[left_idx+len(left):end_idx]
            names.append(entry)
            start_idx = end_idx + 1

    return names


def build_log_file_path(file_path: str):
    """"
    Reads from the BasicConfigurationFile the path for the log file. The folder will be created if it does not exist.
    :return: absolute path to the logging file
    :rtype: str
    """
    file_path = os.path.abspath(file_path)
    try:
        os.makedirs(os.path.dirname(file_path), mode=0o777, exist_ok=True)
    except FileExistsError:
        pass
    except TypeError as te:
        raise te
    except OSError as ose:
        raise ose
    return file_path


def create_console_handler(frmt: str = logging_format, hdlr_lvl=logging.WARNING):
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

    if isinstance(hdlr_lvl, str):
        hdlr_lvl = logging.getLevelName(hdlr_lvl)
    hdlr.setLevel(hdlr_lvl)
    return hdlr


def create_file_handler(file, frmt: str = logging_format):
    """
    Creates a RotatingFileHandler
    :param file:
    :param str frmt: Format string for the log messages
    :return: Returns the created handler
    :rtype: logging.handlers.RotatingFileHandler
    """
    file_path = build_log_file_path(file)
    hdlr = logging.handlers.RotatingFileHandler(filename=file_path, mode='a', maxBytes=524288, backupCount=1)
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    return hdlr
