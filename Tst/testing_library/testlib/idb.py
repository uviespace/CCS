#!/usr/bin/env python3
"""
Functions to use the instrument database
========================================
"""
import logging
import sys

import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl

# create a logger
logger = logging.getLogger(__name__)


# Return the sid of a housekeeping as integer. Sid names of housekeepings are translated into a interger via
# instrument data base (IDB)
#   @param ccs: instance of the CCScom class
#   @param sid: sid of housekeepings <str>
#   @return: sid <int>
def convert_hk_sid(sid):
    """ Convert the SID of housekeeping reports in both ways: int to str and str to int

    :param sid: int or str: SID of a housekeeping as string or as integer
    
    :return: str or int: SID of the housekeeping as string or integer
    """
    assert isinstance(sid, int) or isinstance(sid, str), logger.error('convert_hk_sid: argument sid has to be a integer or string')
    result = None
    if isinstance(sid, str):
        query = cfl.scoped_session_idb().execute('SELECT txp_from FROM txp WHERE txp_altxt="{}"'.format(sid))
        fetch = query.fetchall()
        if len(fetch) != 0:
            result = int(fetch[0][0])
    if isinstance(sid, int):
        # ToDo: replace hardcoded DPKT7030
        query = cfl.scoped_session_idb().execute('SELECT txp_altxt FROM txp WHERE txp_numbr="DPKT7030" AND txp_from="{}"'.format(sid))
        fetch = query.fetchall()
        if len(fetch) != 0:
            result = str(fetch[0][0])
    if result is None:
        logger.error('convert_hk_sid: unknown datapool item {}'.format(sid))
    return result


class DataPoolParameter:
    """

    """
    def __init__(self):
        self.name = None
        self.description = None
        self.pid = None
        self.unit = None
        self.width = None
        self.possible_values = []

        self.value = None

    def add_possible_value(self, range_from, range_to, text):
        """
        Add a entry to the possible vale array

        :param range_from:
        :param range_to:
        :param text:

        :return:
        """
        entry = {
            'range_from': range_from,
            'range_to': range_to,
            'text': text
        }
        self.possible_values.append(entry)

    def assign_value(self, value):
        self.value = cfl.get_calibrated(pcf_name=self.name, rawval=value)

    def log_par(self):
        logger.info('name = {}; width = {}'.format(self.name, self.width))


def get_info_of_data_pool_parameter(name):
    """
    from testlib import idb
    x = idb.get_info_of_data_pool_parameter(name='sdu2State')

    Fetching all information from the instrument database about data pool parameter names.
    Knowing only the name of the parameter, all other information should be collected by database queries.
    :param name: str
        Name of the parameter.
    :return: idb.data_pool_parameter
        Instance of the class data_pool_parameter. Holds the information about the parameter
    """
    parameter = DataPoolParameter()

    # get information from pcf
    query = 'SELECT * from pcf where pcf_descr="{}"'.format(name)
    dbres = cfl.scoped_session_idb().execute(query)
    result = dbres.fetchall()

    if len(result) == 1:
        row = result[0]
        parameter.name = row[0]
        parameter.description = row[1]
        parameter.pid = row[2]
        parameter.unit = row[3]
        parameter.width = row[6]
        txp_number = row[11]
        if txp_number is not None:
            # get the possible values
            query = 'SELECT * from txp where txp_numbr="{}"'.format(txp_number)
            dbres = cfl.scoped_session_idb().execute(query)
            values = dbres.fetchall()
            if len(values) > 0:
                for val in values:
                    parameter.add_possible_value(range_from=val[1], range_to=val[2], text=val[3])

    if len(result) == 1:
        parameter.name = result[0][1]

    parameter.log_par()

    return parameter
