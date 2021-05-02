# import gi
# gi.require_version('Gtk', '3.0')
# from gi.repository import Gtk, Gdk
import json
import data_model
import os
import logging
import toolbox

module_logger = logging.getLogger(__name__)
console_handler = toolbox.create_console_handler()
module_logger.addHandler(console_handler)


def check_file_extension(file_path, extension):
    # see if the extension has a leading dot, if not add it
    if extension is not None and extension[0] != '.':
        extension = '.' + extension
    path = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    # check if the filename has a extension, if not add it
    if file_name.rfind('.') == -1:
        new_file_name = file_name + extension
        file_path = os.path.join(path, new_file_name)
    return file_path


def save_file(file_path, test_spec, file_extension=None, logger=module_logger, *args):
    # check if the file has a extension, if not add it
    file_path = check_file_extension(file_path, file_extension)
    with open(file_path, 'w') as file:
        try:
            json.dump(test_spec, fp=file, indent=1, default=test_spec.serialize)
        except Exception as e:
            logger.exception(e)
            logger.error('Failed to json-dump the instance into a file')
    logger.info('Saved file "{}"'.format(file_path))


def _to_json_string(test_to_save):
    assert isinstance(test_to_save, data_model.TestSequence)
    str = test_to_save.encode_to_json()
    return str


def open_file(file_name, *args):
    data_from_file = None
    with open(file_name, 'r') as file:
        data_from_file = _from_json(file)
    file.close()
    return data_from_file


def _from_json(text_io):
    data = text_io.read()
    decoded_data = json.loads(data)
    return decoded_data
