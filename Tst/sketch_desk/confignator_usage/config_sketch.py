import confignator
import logging
from logging import handlers
import os


logging_format = '%(levelname)s\t%(asctime)s\t%(name)s\t\t%(filename)s\t\t%(message)s'
logging_level = logging.DEBUG


def build_log_file_path():
    """"
    Reads the path to for the file where the logging records are written from the configuration. If this is not
    successful the current working directory is used. The folder will be created if it does not exist.
    :return: absolute path to the logging file
    :rtype: str
    """
    file_name = os.path.abspath('config_editor_sketch_me.log')
    return file_name


def create_console_handler(frmt=logging_format):
    hdlr = logging.StreamHandler()
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(logging.CRITICAL)
    return hdlr


def create_file_handler(frmt=logging_format):
    file_name = build_log_file_path()
    hdlr = logging.FileHandler(filename=file_name, mode='w')
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    return hdlr


logger = logging.getLogger('Config-Sketch-Logger')
logger.setLevel(level=logging_level)
console_hdlr = create_console_handler()
logger.addHandler(hdlr=console_hdlr)
file_hdlr = create_file_handler()
logger.addHandler(hdlr=file_hdlr)


logger.info('--------------------------------------------------------')

c1 = confignator.get_config(file_path='a.cfg', logger=logger)
c2 = confignator.get_config(file_path='b.cfg', logger=logger)

c3 = confignator.get_config(file_path=['a.cfg', 'b.cfg'], logger=logger)
c4 = confignator.get_config(file_path=['b.cfg', 'a.cfg'], logger=logger)

logger.info('c1: {}'.format(c1.get('paths', 'obsw')))
logger.info('c2: {}'.format(c2.get('paths', 'obsw')))
logger.info('c3: {}'.format(c3.get('paths', 'obsw')))
logger.info('c4: {}'.format(c4.get('paths', 'obsw')))

logger.info('--------------------------------------------------------')

cr = confignator.get_config(file_path='d.cfg', logger=logger)
cr.save_to_file('saved_new_d.cfg')

logger.info('--------------------------------------------------------')

cr = confignator.get_config(logger=logger)
cr.save_to_file('saved_without_filepath.cfg')

logger.info('--------------------------------------------------------')
confignator.editor('saved_without_filepath.cfg')
