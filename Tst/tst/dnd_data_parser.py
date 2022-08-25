"""
Creates and parses the data strings for the Drag and Drop of TST.
The data string is build with a separator.
The first part describes the drag source as text.
"""
import logging
import toolbox

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.WARNING)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)

# this separator is used to concatenate data
separator = ';;'
data_type_snippet = 'snippet'
data_type_step = 'step'


def create_datastring(data_type, sequence='', step_number='', description='', comment='', command_code='', verification_code='', verification_descr='', logger=logger):
    if data_type == data_type_snippet:
        step_number = ''
    # build the data string
    try:
        data_string = data_type
        data_string += separator + str(sequence)
        data_string += separator + step_number
        data_string += separator + description
        data_string += separator + comment
        data_string += separator + command_code
        data_string += separator + verification_code
        data_string += separator + verification_descr
    except Exception as excep:
        logger.exception(excep)
        raise excep
    return data_string


def read_datastring(data_string: str, logger=logger) -> dict:
    try:
        data = []
        while data_string.find(separator) != -1:
            separator_index = data_string.find(separator)
            data.append(data_string[:separator_index])
            data_string = data_string[separator_index + len(separator):]
        data.append(data_string)
        data_type = data[0]
        sequence = data[1]
        step_number = data[2]
        description = data[3]
        comment = data[4]
        command_code = data[5]
        verification_code = data[6]
        verification_descr = data[7]
        data_dict = {
            'data_type': data_type,
            'sequence': sequence,
            'step_number': step_number,
            'description': description,
            'comment': comment,
            'command_code': command_code,
            'verification_code': verification_code,
            'verification_descr' : verification_descr
        }
    except Exception as excep:
        logger.exception(excep)
        raise excep
    return data_dict
