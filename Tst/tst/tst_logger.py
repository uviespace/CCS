"""
Configure logging for TST
"""
import logging
import logging.config
import logging.handlers
import os
import confignator

logging_format = '%(levelname)s\t%(asctime)s\t\t%(processName)s\t\t%(name)s\t\t%(message)s'


def set_level(logger):
    assert isinstance(logger, logging.Logger)
    lvl = confignator.get_option(section='tst-logging', option='level')
    logger.setLevel(level=lvl)


def create_console_handler(logger, frmt=logging_format):
    assert isinstance(logger, logging.Logger)
    hdlr = logging.StreamHandler()
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(logging.WARNING)
    logger.addHandler(hdlr=hdlr)


def create_file_handler(logger, frmt=logging_format):
    assert isinstance(logger, logging.Logger)
    file_name = confignator.get_option('tst-logging', 'log-file-path')
    os.makedirs(os.path.dirname(file_name), mode=0o777, exist_ok=True)
    hdlr = logging.handlers.RotatingFileHandler(filename=file_name, mode='a', maxBytes=524288, backupCount=3)
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    logger.addHandler(hdlr=hdlr)
