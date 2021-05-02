import time
import multiprocessing


def my_func(event_a, event_b, *args):
    assert isinstance(event_a, multiprocessing.synchronize.Event)
    p_a = multiprocessing.Process(target=my_step,
                                  name='step a',
                                  args=(evt_b,),
                                  kwargs={})
    p_a.start()
    while event_a.is_set() is False and p_a.exitcode is None:
        time.sleep(1)
    print('process "{}" finished with exit code {}'.format(p_a.name, p_a.exitcode))
    if event_a.is_set():
        print('process "{}" was terminated'.format(p_a.name))
        p_a.terminate()

    return


def my_step(event_b, *args):
    assert isinstance(event_b, multiprocessing.synchronize.Event)
    t_start = time.time()
    j = 0
    while j < 17:
        print('j={}'.format(j))
        j += 1
        time.sleep(1)

    t_end = time.time()
    print('b has FINISHED: needed {}s'.format(t_end - t_start))


if __name__ == '__main__':
    evt_a = multiprocessing.Event()
    evt_b = multiprocessing.Event()
    p_a = multiprocessing.Process(target=my_func,
                                  name='my func',
                                  args=(evt_a, evt_b),
                                  kwargs={})
    p_a.start()

    # stop process by force
    # p_a.terminate()
    # stop process using event
    time.sleep(19)
    evt_a.set()
    pass

"""
Test/Step abortion
==================
To make a test/step able to be aborted/killed they are own processes.
To terminate a process an Event is set.
If a process is terminated, all child processes should be terminated too.

Parallel execution of steps/tests
=================================
A test executes its steps in a sequence. While step 2,3,4,5 are running, a function is executed repeatedly or a set of steps is executed.
Within the test the start point of the parallel process needs to be determined. An Events is used to terminate the parallel process. The first is to kill the parallel process, the second one can be set by the parallel process
"""

