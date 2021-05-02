#!/usr/bin/env python3
"""
Analyzing the log file of the Command Script. Get the information which Steps were done and which TC were sent.
"""
example_log_file = '../logs_test_runs/Simple_Example_command_cmd.log'

import collections
import json
import logging
logger = logging.getLogger(__name__)

hardcoded_keyword = '#SENT TC'


def key_word_found(line):
    """
    Searches for the key_word in the provided string.
    :param str line: string which should be checked for key_word
    :return: True if key_word was found
    :rtype: bool
    """
    assert isinstance(line, str)
    if line.find(hardcoded_keyword) == -1:
        found = False
    else:
        found = True
    return found


class TcId:
    """
    This class is a collection of information for a sent TC. It can be used to identify a TC in the packet pool.
    Following information is stored:

    * service type (st)
    * subservice type (sst)
    * application id (apid)
    * source sequence counter (ssc)
    * timestamp when the telecommand was sent (CUC timestamp of the last packet in the pool before the TC packet)

    Further it provides methods to encode this information in a JSON string and a method to parse from a JSON string.
    This has the purpose to write and read log files.
    """
    key_word = hardcoded_keyword

    def __init__(self, st=None, sst=None, apid=None, ssc=None, timestamp=None):
        self.st = st
        self.sst = sst
        self.apid = apid
        self.ssc = ssc
        self.timestamp = timestamp

    def tc_id_tuple(self):
        """
        Returns a tuple of telecommand identifier attributes
        :return: telecommand identifier attributes
        :rtype: tuple
        """
        tc_id_tup = (self.apid, self.ssc, self.timestamp)
        return tc_id_tup

    def tc_kind(self):
        """
        Returns the service type and subservice type of the TC as string.
        :return:  String like "TC(3,1)"
        :rtype: str
        """
        tc_kind = 'TC({},{})'.format(self.st, self.sst)
        return tc_kind

    def json_dump_for_logging(self):
        od = collections.OrderedDict([('st', self.st),
                                      ('sst', self.sst),
                                      ('ssc', self.ssc),
                                      ('apid', self.apid),
                                      ('timestamp', self.timestamp)])
        json_string = '{} {}'.format(self.key_word, json.dumps(od))
        return json_string

    def parse_tc_id_from_json_string(self, line):
        """
        From a line of the log containing the JSON string of a sent TC following information is extracted:

        * service type (st)
        * sub-service type (sst)
        * application id (apid)
        * source sequence counter (ssc)
        * timestamp when the telecommand was sent (CUC timestamp of the last packet in the pool before the TC packet)

        From the position of the key_word string the first occurring curly bracket is used as start of the JSON string.
        It is assumed that after the key_word, there is the JSON string only. The string is parsed into a dictionary
        and then the data is written into the TcId instance.
        :param str line: a line of the log file
        """
        assert isinstance(line, str)

        keyword_index = line.find(self.key_word)
        start_bracket = line.find('{', keyword_index)

        if keyword_index != -1:
            try:
                # parse the string into a dictionary
                data = json.loads(line[start_bracket:])
                # read the data from the dictionary and assign it to the attributes of the instance
                try:
                    self.st = data['st']
                except KeyError:
                    logger.warning('parse_tc_id_from_json_string: could not parse the Service Type of the TC.'
                                   ' After parsing, the key in the dictionary could not be found.')
                try:
                    self.sst = data['sst']
                except KeyError:
                    logger.warning('parse_tc_id_from_json_string: could not parse the Sub Service Type of the TC.'
                                   'After parsing, the key in the dictionary could not be found.')
                try:
                    self.ssc = data['ssc']
                except KeyError:
                    logger.warning('parse_tc_id_from_json_string: could not parse the Source Sequence Counter of the TC.'
                                   'After parsing, the key in the dictionary could not be found.')
                try:
                    self.apid = data['apid']
                except KeyError:
                    logger.warning('parse_tc_id_from_json_string: could not parse the Application ID of the TC. '
                                   'After parsing, the key in the dictionary could not be found.')
                try:
                    self.timestamp = data['timestamp']
                except KeyError:
                    logger.warning('parse_tc_id_from_json_string: could not parse the Timestamp of the TC. '
                                   'After parsing, the key in the dictionary could not be found.')
            except json.decoder.JSONDecodeError:
                logger.error('parse_tc_id_from_json_string: parsing of the TC JSON string failed!')
