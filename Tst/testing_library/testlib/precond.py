#!/usr/bin/env python3
"""
Preconditions
=============
"""
import logging

from . import report
from . import sim
from . import tm
from . import tools

import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl

# create logger
logger = logging.getLogger(__name__)


def get_states(pool_name, silent=False):
    """
    Returns the states of IASW, SEM and SEM_Operational state machine
    :param pool_name: str
        Name of the pool for TM/TCs in the database
    :return: str, str, str
        Returns the values of iaswState, semState, semOperState
    """
    state_iasw = None
    state_sem = None
    state_sem_oper = None

    hk_name = 'IFSW_HK'
    state_names = ['iaswState', 'semState', 'semOperState']

    if state_names is not None:
        # fetch the house keeping report entries
        states = tm.get_hk_entry(pool_name=pool_name, hk_name=hk_name, name=state_names, silent=silent)

        # check if the states could be found
        if states is not None and 'iaswState' in states[0]:
            state_iasw = states[0]['iaswState']
        if states is not None and 'semState' in states[0]:
            state_sem = states[0]['semState']
        if states is not None and 'semOperState' in states[0]:
            state_sem_oper = states[0]['semOperState']
    if state_iasw is None or state_sem is None or state_sem_oper is None:
        logger.warning('get_states: could not retrieve all of the states: IASW state, SEM state, SEM oper state!')

    return state_iasw, state_sem, state_sem_oper


def iasw_standby(pool_name, silent=False):
    """
    precondition: 'Nominal operation in STANDBY mode'
    :param pool_name: <str>: name of the pool
    :return: <boolean>: True if the precondition are fulfilled
    """
    success = False

    # get states
    iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name, silent=silent)

    # if the IASW is a other mode: shut down the SEM (if running) and command IASW into STANDBY
    if iasw == 'SEM_OFFLINE' or iasw == 'PRE_SCIENCE' or iasw == 'SCIENCE':
        # check if the SEM is running
        sem_runs = sim.sem_runs()
        if sem_runs:
            # command SEM to shut of
            switch_off_sem(pool_name=pool_name)
        # command IASW into Standby
        cfl.TcStopSem() #TODO: project specific command -- has to be done another way
        logger.info('command IASW into STANDBY')
        # get states again
        iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name)

    # check if the conditions are fulfilled
    if iasw == 'STANDBY':
        success = True

    return success


def sem_safe_mode(pool_name):
    """
    Verify that the IASW is in SAFE.
    If IASW is in a other mode, command it to SAFE.
    :param pool_name: str
        Name of the pool for telemetry and telecommand packets in the database
    :return: boolean
        True if IASW is in mode SAFE
    """
    success = False
    crsem = None

    # check the current states
    iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name)

    # if SEM is not in mode SAFE, do the steps to bring it into it
    if state_sem != 'SAFE':
        # check if the CrSem process is running
        sem_runs = sim.sem_runs()
        if not sem_runs:
            # send TC to switch on the SEM
            tc_on = cfl.Tcsend_DB('DPU_IFSW_START_OFFLINE_O', ack='0b1011', pool_name=pool_name)
            t_tc_on = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=tc_on)
            # switch on the SEM simulator
            crsem = sim.start_sem_w_fits()
            # wait for the event when the SEM to enter INIT
            trans_1 = {'SrcSemSt': 'OFF', 'DestSemSt': 'INIT'}
            evt_init = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEM_TR', entries=trans_1,
                                      t_from=t_tc_on, duration=20)
            # wait for the event when the SEM enters OPER
            trans_2 = {'SrcSemSt': 'INIT', 'DestSemSt': 'OPER'}
            evt_oper = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEM_TR', entries=trans_2,
                                      t_from=t_tc_on, duration=20)

    # check if IASW is in OPER and go into SAFE
    state_sem = tm.get_hk_entry(pool_name=pool_name, hk_name='IFSW_HK', name='semState', silent=True)
    if tools.entry_is_equal(entry=state_sem, key_value={'semState': 'OPER'}):
        # send TC(192,10) command to bring SEM into SAFE
        tc_safe = cfl.Tcsend_DB('DPU_IFSW_GO_SAFE', ack='0b1011', pool_name=pool_name)
        t_tc_save = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=tc_safe)
        # wait for the event when the SEM to enter SAFE
        trans_3 = {'SrcSemSt': 'OPER', 'DestSemSt': 'SAFE'}
        evt_init = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEM_TR', entries=trans_3,
                                  t_from=t_tc_save, duration=20)

    # verify that the SEM is now in SAFE
    expected = {'semState': 'SAFE'}
    state_sem = tm.get_hk_entry(pool_name=pool_name, hk_name='IFSW_HK', name='semState', silent=True)
    if tools.entry_is_equal(entry=state_sem, key_value=expected):
        # log the current states
        iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name)
        success = True

    return success


def any_iasw_state(pool_name):
    """
    Precondition: 'Nominal operation in any IASW mode'.
    :param pool_name: str
        Name of the pool for TM/TCs in the database
    :return: bool
        True if the precondition are fulfilled
    """
    success = False

    # get the current states
    iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name)

    # check if preconditions are fulfilled
    if iasw == 'SEM_OFFLINE' or iasw == 'STANDBY' or iasw == 'PRE_SCIENCE' or iasw == 'SCIENCE':
        success = True

    return success


def switch_off_sem(pool_name):
    """
    Send the TC() to switch off the SEM. Wait for the transition events EVT_SEM_TR:
    * 'SrcSemSt': 'OPER',     'DestSemSt': 'SHUTDOWN'
    * 'SrcSemSt': 'SHUTDOWN', 'DestSemSt': 'OFF'

    :param pool_name: str
        Name of the pool for TC/TMs in the database
    :return: bool
        True if SEM transition events OPER->SHUTDOWN, SHUTDOWN->OFF were received and the semState is OFF
    """
    result = None
    event_shutdown = None
    event_off = None
    sem_state = None

    # switch off the SEM
    sem_off = cfl.Tcsend_DB('DPU_IFSW_SWCH_OFF_SEM', ack='0b1011', pool_name=pool_name)
    logger.info('Terminating SEM simulator process')
    sim.stop_sem(None)
    tm.check_acknowledgement(pool_name=pool_name, tc_identifier=sem_off)

    # check if a TM(1,7) was received for this TC
    suc, acknow = tm.await_tc_acknow(pool_name=pool_name, tc_identifier=sem_off, tm_st=1, tm_sst=7)
    if len(acknow) > 0:
        logger.info('Command was accepted, started, terminated. Received TM(1,7)')
        t_sem_off = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=sem_off)

        # get event EVT_SEM_TR with
        transistion_1 = {'SrcSemSt': 'OPER', 'DestSemSt': 'SHUTDOWN'}
        event_shutdown = tm.await_event(severity=cfl.EVENT_SEVERITY_NORMAL, event_id='EVT_SEM_TR',# TODO: EVENT_SEVERITY has to be defined elsewhere
                                        pool_name=pool_name, t_from=t_sem_off, entries=transistion_1)

        # get event EVT_SEM_TR with
        transistion_2 = {'SrcSemSt': 'SHUTDOWN', 'DestSemSt': 'OFF'}
        event_off = tm.await_event(severity=cfl.EVENT_SEVERITY_NORMAL, event_id='EVT_SEM_TR',# TODO: EVENT_SEVERITY has to be defined elsewhere
                                   pool_name=pool_name, t_from=t_sem_off, entries=transistion_2)

        if len(event_shutdown) > 0 and len(event_off) > 0:
            t_event_1 = cfl.get_cuctime(event_shutdown)
            t_event_2 = cfl.get_cuctime(event_off)
            time_diff = t_event_2 - cfl.get_cuctime(t_sem_off)
            logger.info('Time difference between TC acknowledgement and event EVT_SEM_TR (OFF): {}s'.format(time_diff))

            # verify that the SEM state machine is in state OFF
            sem_state_machine = tm.get_hk_entry(pool_name=pool_name, hk_name='IFSW_HK', name='semState',
                                                t_from=t_event_2)
            if sem_state_machine is not None and 'semState' in sem_state_machine[0]:
                if sem_state_machine[0]['semState'] == 'OFF':
                    sem_state = True

    if event_shutdown is not None and len(event_shutdown) > 0:
        if event_off is not None and len(event_off) > 0:
            if sem_state:
                result = True

    return result


def iasw_semoffline_semoper_standby(pool_name):
    """ 
    Establish the precondition: Nominal operation with 
    * IASW state machine in 'SEM_OFFLINE' 
    * SEM state machine in 'OPER'
    * SEM Operational state machine in 'STANDBY'
    Steps which are done by this function:
    * Getting the current states of IASW state machine, SEM state machine and SEM Operational state machine.
    * Check if the IASW is in state 'STANDBY'. If it is not in this state, command it into it.
      Waiting for the event when the IASW enters 'STANDBY'
    * Check if the SEM simulator process is running and start it if it is not running. 
      Only done if the simulators are used.
    * If the SEM is in state 'OFF', the SEM is commanded to start into SEM_OFFLINE.
      Waiting for the SEM events when entering 'INIT' and 'OPER'.
      Waiting for the SEM Operational event when entering 'STANDBY'.
    * Check the states again to verify if the preconditions are satisfied.
    
    :param pool_name: str
        Name of the pool in the database where TC/TMs are stored
    :return: bool, subprocess.Popen
        True if the preconditions are fulfilled, Process of the SEM simulator
    """
    success = False

    # get the states
    state_iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name)

    # check if the preconditions are already fulfilled
    if state_iasw == 'SEM_OFFLINE' and state_sem == 'OPER' and state_sem_oper == 'STANDBY':
        logger.info('Preconditions are fulfilled\n')
        success = True
    else:
        # if IASW is in another state than STANDBY, command it into it
        if state_iasw != 'STANDBY':
            # command IASW into Standby
            logger.info('Command IASW into STANDBY')
            tc_stop = cfl.TcStopSem() # TODO: too project specific -- replace
            t_tc_stop = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=tc_stop)
            # wait for the event when the IASW enters STANDBY
            trans = {'DestIaswSt': 'STANDBY'}
            evt_stop = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_IASW_TR',
                                      entries=trans, t_from=t_tc_stop, duration=10)

        # check if the CrSem process is already running
        sem_runs = sim.sem_runs()
        if sem_runs is False:
            # switch on the SEM simulator
            crsem = sim.start_sem_w_fits()
        else:
            logger.info('CrSem is already running')

        # check if the state of the SEM is OFF
        sem_state = tm.get_hk_entry(pool_name=pool_name, hk_name='IFSW_HK', name='semState', silent=True)
        expect = {'semState': 'OFF'}
        if tools.entry_is_equal(entry=sem_state, key_value=expect):
            # command IASW into SEM_OFFLINE if it is in STANDBY
            expected = {'iaswState': 'STANDBY'}
            iasw_state = tm.get_hk_entry(pool_name=pool_name, hk_name='IFSW_HK', name=expected, silent=True)
            if tools.entry_is_equal(entry=iasw_state, key_value=expected):
                logger.info('Command IASW into SEM_OFFLINE')
                tc_on = cfl.Tcsend_DB('DPU_IFSW_START_OFFLINE_O', ack='0b1011', pool_name=pool_name)
                # check that the command was successful accepted, started, terminated
                tm.check_acknowledgement(pool_name=pool_name, tc_identifier=tc_on)
                t_tc_on = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=tc_on)
                # wait for the events of the SEM start up events
                if t_tc_on is not None:
                    logger.info('Waiting for the events of the SEM to enter INIT -> OPER and for SemOp to enter STANDBY')
                    # wait for the event when the SEM to enter INIT
                    trans_1 = {'SrcSemSt': 'OFF', 'DestSemSt': 'INIT'}
                    evt_init = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEM_TR',
                                              entries=trans_1, t_from=t_tc_on, duration=2)
                    # wait for the event when the SEM enters OPER
                    trans_2 = {'SrcSemSt': 'INIT', 'DestSemSt': 'OPER'}
                    evt_oper = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEM_TR',
                                              entries=trans_2, t_from=t_tc_on, duration=60)
                    # wait for the event when the SEM operational enters STANDBY
                    trans_3 = {'DestSemOpSt': 'STANDBY'}
                    evt_stan = tm.await_event(pool_name=pool_name, severity=1, event_id='EVT_SEMOP_TR',
                                              entries=trans_3, t_from=t_tc_on, duration=2)

        # get the states again
        state_iasw, state_sem, state_sem_oper = get_states(pool_name=pool_name)
        # check if preconditions are fulfilled
        if state_iasw == 'SEM_OFFLINE' and state_sem == 'OPER' and state_sem_oper == 'STANDBY':
            success = True

    return success


def sem_oper_go_stabilize(pool_name, await_event=True):
    """
    bring the SEM Operational State Machine into STABILIZE
    :param pool_name: str
        Name of the pool for TC/TM in the database
    :param await_event: bool
        If set to True the function waits for the event when the SEM Operational state machine enters
        STABILIZE.
    :return: bool
        True if the event was received
    """
    success = False
    logger.info('bring SEM Operational State Machine into STABILIZE')
    # send TC(192,3) to order the SEM Operational State Machine into STABILIZE
    tc = cfl.Tcsend_DB('DPU_IFSW_GO_STAB', ack='0b1011', pool_name=pool_name)
    t_tc = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=tc)
    # check if the command was successful by looking for acknowledgement packets
    ack = tm.check_acknowledgement(pool_name=pool_name, tc_identifier=tc)

    # verify the transition of the SEM Operational State Machine into STABILIZE
    if await_event is True:
        par = {'SrcSemOpSt': 'TR_STABILIZE', 'DestSemOpSt': 'STABILIZE'}
        event = tm.await_event(pool_name=pool_name,
                               severity=1,
                               event_id='EVT_SEMOP_TR',
                               entries=par,
                               duration=60,
                               t_from=t_tc)
        if len(event) > 0:
            success = True
    return success


def pre_science_stabilize(pool_name):
    """
    This function sends the command to enter PRE_SCIENCE.
    The SEM event forwarding is enabled and at the end of this function disabled again.
    If the SEM does not run, it is started and checked if the events EVT_PRG_APS_BT and EVT_PRG_CFG_LD is received.
    The state machines have to be in the states
        * iaswState in STANDBY
        * semState in OFF
        * semOperState in STOPPED
    Then the command to go into PRE_SCIENCE is sent.
    The events of entering PRE_SCIENCE and STABILIZE are awaited. If they are received the function returns True.

    :param pool_name: str
        Name of the data pool for TM/TCs in the database
    :return: bool
        True if the IASW state machine is in PRE_SCIENCE and the SemOperational state machine is in STABILIZE
    """
    success = False

    logger.info('pre_science_stabilize: try to command IASW in state PRE_SCIENCE and SEM in state STABILIZE')
    wait = 180
    event_iasw = None
    event_sem_op = None

    # enable SEM event forwarding
    logger.info('pre_science_stabilize: enable the SEM event forwarding')
    tc_for = cfl.Tcsend_DB('DPU_IFSW_UPDT_PAR_BOOL', 4,
                           'SEM_SERV5_1_FORWARD', 'TYPE_BOOL', 0, 1,
                           'SEM_SERV5_2_FORWARD', 'TYPE_BOOL', 0, 1,
                           'SEM_SERV5_3_FORWARD', 'TYPE_BOOL', 0, 1,
                           'SEM_SERV5_4_FORWARD', 'TYPE_BOOL', 0, 1,
                           ack='0b1011')
    tm.check_acknowledgement(pool_name=pool_name, tc_identifier=tc_for)

    if not sim.sem_runs():
        # start the CrSem (with fits or with the data simulator)
        logger.info('pre_science_stabilize: starting CrSem ...')
        t_sem_start = cfl.get_last_pckt_time(pool_name=pool_name, string=False)
        sim.start_sem_w_fits()

        # wait for the CrSem to boot and load the configuration
        sem_event_1 = 'EVT_PRG_APS_BT'
        sem_event_2 = 'EVT_PRG_CFG_LD'
        logger.info('pre_science_stabilize: waiting for the CrSem to boot and load the configuration (events {} and {})'
                 .format(sem_event_1, sem_event_2))
        event_1 = tm.await_event(severity=cfl.EVENT_SEVERITY_NORMAL, event_id=sem_event_1, #TODO: EVENT_SEVERITY not in cfl anymore
                                 pool_name=pool_name, duration=wait, t_from=t_sem_start)
        event_2 = tm.await_event(severity=cfl.EVENT_SEVERITY_NORMAL, event_id=sem_event_2, #TODO: EVENT_SEVERITY not in cfl anymore
                                 pool_name=pool_name, duration=wait, t_from=t_sem_start)

    # check if the IASW, SEM and SEM operational are in the correct states to command them into PRE_SCIENCE
    expected_states = {
        'iaswState': 'STANDBY',
        'semState': 'OFF',
        'semOperState': 'STOPPED'
    }
    logger.info('pre_science_stabilize: current states are')
    entries = tm.get_hk_entry(pool_name=pool_name, hk_name='IFSW_HK', name=expected_states, silent=True)
    ready = tools.entry_is_equal(entry=entries, key_value=expected_states)

    # if the CrSem is ready, send the TC to prepare for science
    if ready:
        # a) command the IASW into PRE_SCIENCE and the SEM into STABILIZE with TC(193,1)
        logger.info('pre_science_stabilize: command IASW into PRE_SCIENCE...')
        prepare_tc = cfl.Tcsend_DB('DPU_IFSW_PREPARE_SCI', ack='0b1011', pool_name=pool_name)
        tm.check_acknowledgement(pool_name=pool_name, tc_identifier=prepare_tc)
        t_tc_presci = tm.time_tc_accepted(pool_name=pool_name, tc_identifier=prepare_tc)

        # b) wait for the event: IASW is in state PRE_SCIENCE
        req_event_i = 'EVT_IASW_TR'
        req_state_i = {'DestIaswSt': 'PRE_SCIENCE'}
        event_iasw = tm.await_event(severity=cfl.EVENT_SEVERITY_NORMAL, event_id=req_event_i, #TODO: EVENT_SEVERITY not in cfl anymore
                                    pool_name=pool_name, duration=wait, t_from=t_tc_presci, entries=req_state_i)
        # log the event TM packet
        if len(event_iasw) > 0:
            report.print_event_data_tuple(tm_packets=event_iasw)
        else:
            logger.warning('pre_science_stabilize: waited for IASW to go into the state PRE_SCIENCE for {}s.'
                        'No event report was received.'.format(wait))

        # c) wait for the event: SEM is in state STABILIZE
        req_event_s = 'EVT_SEMOP_TR'
        req_state_s = {'DestSemOpSt': 'STABILIZE'}
        event_sem_op = tm.await_event(severity=cfl.EVENT_SEVERITY_NORMAL, event_id=req_event_s, #TODO: EVENT_SEVERITY not in cfl anymore
                                      pool_name=pool_name, duration=wait, t_from=t_tc_presci, entries=req_state_s)
        # log the event TM packet
        if len(event_sem_op) > 0:
            report.print_event_data_tuple(tm_packets=event_sem_op)
        else:
            logger.warning('pre_science_stabilize: waited for SEM to go into the state STABILIZE for {}s.'
                        'No event report was received.'.format(wait))

    else:
        logger.warning('pre_science_stabilize: state machines are not in the correct states to command the IFSW into '
                    'PRE_SCIENCE')

    # disable SEM event forwarding
    logger.info('pre_science_stabilize: disable the SEM event forwarding')
    tc_dis = cfl.Tcsend_DB('DPU_IFSW_UPDT_PAR_BOOL', 4,
                           'SEM_SERV5_1_FORWARD', 'TYPE_BOOL', 0, 0,
                           'SEM_SERV5_2_FORWARD', 'TYPE_BOOL', 0, 0,
                           'SEM_SERV5_3_FORWARD', 'TYPE_BOOL', 0, 0,
                           'SEM_SERV5_4_FORWARD', 'TYPE_BOOL', 0, 0,
                           ack='0b1011')
    tm.check_acknowledgement(pool_name=pool_name, tc_identifier=tc_for)

    # if both events were received this procedure was successful
    if len(event_iasw) > 0 and len(event_sem_op) > 0:
        success = True

    return success
