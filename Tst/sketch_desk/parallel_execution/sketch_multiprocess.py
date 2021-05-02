#!/usr/bin/python
"""
Doing tasks in parallel is a requirement. Following functionality should be fulfilled:

    * every step should be its own thread/process
    * running two or more steps in parallel
    * start/stop steps by events
    * every step should be able to be aborted
    * all steps should log into one file (?)

Control of the processes: start, force stop from outside, emit event/signal from within the process
How to abort a step?
If steps are executed as processes: How to do the logging?
If parallel tests (as GTK application) are run, how to do the logging?
"""
import time
import multiprocessing
import logging
import toolbox

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)
file_hdlr = toolbox.create_file_handler(file='sketch_multiprocess.log')
logger.addHandler(hdlr=file_hdlr)


def print_stats_event(events: list):
    logger.debug('events are set: {}'.format([evt.is_set() for evt in events]))


def step_a(*args):
    t_start = time.time()
    
    def tell_me(counter):
        logger.debug('counter={}'.format(counter))
        time.sleep(counter)
        counter += t
        return counter

    t = 1
    counter = 0

    counter = tell_me(counter)
    counter = tell_me(counter)
    counter = tell_me(counter)
    counter = tell_me(counter)
    counter = tell_me(counter)
    counter = tell_me(counter)
    counter = tell_me(counter)
    counter = tell_me(counter)

    t_end = time.time()
    logger.debug('a has FINISHED: needed {}s'.format(t_end-t_start))


def step_b(*args):
    t_start = time.time()
    j = 0
    while j < 7:
        logger.debug('j={}'.format(time.time(), j))
        if j > 10 and evt_a.is_set():
            break
        j += 1
        time.sleep(1)

    t_end = time.time()
    logger.debug('b has FINISHED: needed {}s'.format(t_end-t_start))


def step_c_para(evt, *args):
    t_start = time.time()
    j = 0
    while not evt.is_set():
        logger.debug('j={}'.format(j))
        j += 1
        time.sleep(1)
    t_end = time.time()
    logger.debug('c has FINISHED: needed {}s'.format(t_end-t_start))


def line_1():
    p1 = create_process_a(evt_a)
    p2 = create_process_b(evt_b)
    p1.start()
    p1.join()
    p2.start()
    p2.join()
    # while p1.is_alive() or p2.is_alive():
    #     logger.debug('line 1: {}'.format(multiprocessing.active_children()))
    #     time.sleep(1)
    evt_c.set()


def line_2():
    p3 = create_process_c(evt_c)
    p3.start()
    while p3.is_alive():
        logger.debug(multiprocessing.active_children())
        time.sleep(1)


def wrapper_process_line_1():
    process = multiprocessing.Process(target=line_1,
                                      name='line 1',
                                      args=(),
                                      kwargs={})
    return process


def wrapper_process_line_2():
    process = multiprocessing.Process(target=line_2,
                                      name='line 2',
                                      args=(),
                                      kwargs={})
    return process


def create_process_a(evt_a):
    process = multiprocessing.Process(target=step_a,
                                      name='step a',
                                      args=(evt_a,),
                                      kwargs={})

    return process


def create_process_b(evt_b):
    p2 = multiprocessing.Process(target=step_b,
                                 name='step b',
                                 args=(evt_b,),
                                 kwargs={})
    return p2


def create_process_c(evt_c):
    pc = multiprocessing.Process(target=step_c_para,
                                 name='step c',
                                 args=(evt_c,),
                                 kwargs={})
    return pc


if __name__ == '__main__':

    evt_a = multiprocessing.Event()
    evt_b = multiprocessing.Event()
    evt_c = multiprocessing.Event()
    print_stats_event([evt_a, evt_b, evt_c])

    w1 = wrapper_process_line_1()
    w1.start()
    w2 = wrapper_process_line_2()
    w2.start()

    while True:
        logger.debug('control loop: {}'.format(multiprocessing.active_children()))
        # print_stats_event([evt_a, evt_b, evt_c])
        if not w1.is_alive() and not w2.is_alive():
            break
        time.sleep(1)

    w1.join()
