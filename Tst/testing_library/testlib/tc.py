"""
Telecommands
============

This module contains functions which have to do with sending telecommands.
"""

import logging
import time
import sys

import confignator
ccs_path = confignator.get_option('paths', 'ccs')
sys.path.append(ccs_path)

import ccs_function_lib as cfl

from . import tm

# create a logger
logger = logging.getLogger(__name__)


def generate_stream_of_tc_6_5(pool_name, duration=300):
    """
    Generating a stream of TC(6,5). Aim to to send one TC(6,5) per cycle (one cycle lasts for 0.125ms)

    :param pool_name: str
        Name of the pool for TM/TCs in the database
    :param duration: int
        Duration of the generaterion in seconds
    :return bool
        True if the time difference between two TC is: 0.125 < differ < 0.250
    """
    # generate a stream of TC for 5 minutes
    PAR_MEMORY_ID_DUMP = 'RAM'
    PAR_START_ADDRESS_DUMP = 0x40000000
    PAR_BLOCK_LENGTH_DUMP = 4

    logger.info('going to create a stream of TC(6,5), see you in {}s...'.format(duration))

    start_time = time.time()
    time_past = 0
    start_time = time.time()
    last_time = None
    ts_sent_tcs = []
    sent_tcs = []
    while time_past < duration:
        # note the current time
        current_time = time.time()

        # wait if the difference between last and current is smaller than a cycle
        if last_time is not None:
            diff = current_time - last_time
            if diff < 0.125:
                time.sleep(0.125 - diff)

        # send TC(6,5) and note the current time again
        current_time = time.time()
        #tc = ccs.Tcsend_DB('SES CMD_Memory_Dump',
        tc = cfl.Tcsend_DB('SES CMD_Memory_Dump',
                           PAR_MEMORY_ID_DUMP,
                           PAR_START_ADDRESS_DUMP,
                           PAR_BLOCK_LENGTH_DUMP,
                           ack='0b1011',
                           pool_name=pool_name,
                           sleep=0)
        sent_tcs.append(tc)
        ts_sent_tcs.append(current_time)
        # note the time of this round, to use it in the next one
        last_time = current_time
        time_past = current_time - start_time

    logger.info('duration of the while loop: {}'.format(last_time - start_time))
    logger.info('number of sent TC(6,5): {}'.format(len(sent_tcs)))

    # check if the TC were generated one per cycle (using local time and not CUC timestamps)
    in_time = False
    not_on_time = False
    logger.debug('differences of the TCs timestamps (local time):')
    for i in range(len(ts_sent_tcs)):
        if i != 0:
            differ = ts_sent_tcs[i] - ts_sent_tcs[i - 1]
            if 0.125 < differ < 0.250:
                logger.debug('{}s'.format(differ))
                in_time = True
            else:
                logger.debug('{}s \tdifference of the timestamps of TCs is not within one cycle'.format(differ))
                not_on_time = True
    if not_on_time:
        in_time = False

    return in_time, sent_tcs


def reset_housekeeping(pool_name, name):
    """
    Reset a housekeeping. Set its generation frequency back to its default value. Set back its enable-status
    back to its default value (by default only IFSW_HK is enabled)

    :param pool_name: str
        Name of the pool for TM/TCs in the database
    :param name: str
        Name of the housekeeping like IFSW_HK, IASW_DG, IASW_PAR, IBSW_DG, IBSW_PAR, ABS_SEM_HK
    :return: bool
        True if all commands were successful with a TM(1,7)
    """
    assert isinstance(name, str)
    success = False

    # ToDo: this hardcoded data should be replaced with a database call
    logger.debug('# ToDo: this function contains hardcoded data, it should be replaced with a database call (if possible)')
    sids = {
        'IFSW_HK': 1,
        'IASW_PAR': 2,
        'IASW_DG': 3,
        'IBSW_DG': 4,
        'IBSW_PAR': 5,
        'SEM_ABS_HK': 6
    }
    default_frequencies = {
        'IFSW_HK': 32,
        'IASW_PAR': 0,
        'IASW_DG': 32,
        'IBSW_DG': 8,
        'IBSW_PAR': 0,
        'SEM_ABS_HK': 160
    }
    default_enabled = {
        'IFSW_HK': True,
        'IASW_PAR': False,
        'IASW_DG': False,
        'IBSW_DG': False,
        'IBSW_PAR': False,
        'SEM_ABS_HK': False
    }

    hk_sid = None
    hk_enabled = None
    hk_freq = None

    set_freq = False
    disabled = False
    enabled = False

    # get the sid
    if name in sids:
        hk_sid = sids[name]
    # get the default enabled status
    if name in default_enabled:
        hk_enabled = default_enabled[name]
        # get the default frequency
    if name in default_frequencies:
        hk_freq = default_frequencies[name]

    # send TC(3,131) and TC(3,5)/TC(3,6)
    if hk_sid is not None and hk_freq is not None and hk_enabled is not None:
        # set the generation frequency to back to its default value
        logger.info('set the generation frequency of {} back to its default value of {} cycles ({}Hz)'
                 .format(name, hk_freq, hk_freq/8))
        #tc_freq = ccs.TcSetHkRepFreq(sid=hk_sid, period=hk_freq)
        tc_freq = cfl.TcSetHkRepFreq(sid=hk_sid, period=hk_freq)
        set_freq, ack_freq = tm.await_tc_acknow(pool_name=pool_name, tc_identifier=tc_freq, tm_sst=7)

        # disable or enable the housekeeping
        if hk_enabled is True:
            # send TC(3,5) to enable the housekeeping report
            logger.info('enable the {} housekeeping report'.format(name))
            #tc_enb = ccs.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', hk_sid, ack='0b1011', pool_name=pool_name)
            tc_enb = cfl.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', hk_sid, ack='0b1011', pool_name=pool_name)
            enabled, ack_enb = tm.await_tc_acknow(pool_name=pool_name, tc_identifier=tc_enb, tm_sst=7)

        if hk_enabled is False:
            # send TC(3,5) to disable the housekeeping report
            logger.info('disable the {} housekeeping report'.format(name))
            #tc_dis = ccs.Tcsend_DB('DPU_IFSW_DIS_HK_DR_GEN', hk_sid, ack='0b1011', pool_name=pool_name)
            tc_dis = cfl.Tcsend_DB('DPU_IFSW_DIS_HK_DR_GEN', hk_sid, ack='0b1011', pool_name=pool_name)
            disabled, ack_dis = tm.await_tc_acknow(pool_name=pool_name, tc_identifier=tc_dis, tm_sst=7)

    # evaluate if the function was successful
    if set_freq:
        if hk_enabled is True:
            if enabled:
                success = True
        if hk_enabled is False:
            if disabled:
                success = True

    return success


def reset_all_housekeepings(pool_name):
    """
    This function resets all housekeepings. The frequencies are set to their default value. The enabled status is set
    back to its default value.

    :param poolname: str
        Name of the pool for TM/TCs in the database
    :return: bool
        True if all commands were successful with a TM(1,7)
    """
    success = False

    # ToDo: this hardcoded data should be replaced with a database call
    logger.debug('# ToDo: this function contains hardcoded data, it should be replaced with a database call (if possible)')
    housekeepings = [
        'IFSW_HK',
        'IASW_PAR',
        'IASW_DG',
        'IBSW_DG',
        'IBSW_PAR',
        'SEM_ABS_HK'
    ]

    # reset all housekeepings
    result = []
    for hk_name in housekeepings:
        suc = reset_housekeeping(pool_name=pool_name, name=hk_name)
        result.append(suc)
        if suc:
            logger.debug('reset_all_housekeepings: reset of {} was successful'.format(hk_name))
        else:
            logger.debug('reset_all_housekeepings: reset of {} failed'.format(hk_name))

    # evaluate if the function was successful
    one_failed = False
    for item in result:
        if item is True:
            success = True
        if item is False:
            one_failed = True
    if one_failed:
        success = False

    return success


def stop_sem(pool_name):
    """
    The TC (193,4) is sent to stop the SEM. Two events are awaited EVT_IASW_TR with DestIaswSt = STANDBY and
    EVT_SEM_TR with DestSemSt = OFF.

    :param pool_name:
    :return:
    """
    result = False

    # send TC(193,4) to stop SEM
    #tc_stop = ccs.Tcsend_DB('DPU_IFSW_STOP_SEM', ack='0b1011', pool_name=pool_name)
    tc_stop = cfl.Tcsend_DB('DPU_IFSW_STOP_SEM', ack='0b1011', pool_name=pool_name)
    t_tc_stop = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=tc_stop)
    # sim.stop_sem(sem=None) ???
    entry_iasw = {'DestIaswSt': 'STANDBY'}
    evt_iasw = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_IASW_TR', entries=entry_iasw,
                              duration=20, t_from=t_tc_stop - 1)
    entry_sem = {'DestSemSt': 'OFF'}
    evt_sem = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEM_TR', entries=entry_sem,
                             duration=20, t_from=t_tc_stop - 1)
    if len(evt_iasw) > 0 and len(evt_sem) > 0:
        result = True

    return result