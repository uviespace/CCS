# You'll need these imports in your own code
import logging
import logging.handlers
import multiprocessing

# Next two import lines for this demo only


#
# Because you'll want to define the logging configurations for listener and workers, the
# listener and worker process functions take a configurer parameter which is a callable
# for configuring logging for that process. These functions are also passed the queue,
# which they use for communication.
#
# In practice, you can configure the listener however you want, but note that in this
# simple example, the listener does not apply level or filter logic to received records.
# In practice, you would probably want to do this logic in the worker processes, to avoid
# sending events which would be filtered out between processes.
#
# The size of the rotated files is made small so you can see the results easily.
def listener_configurer():
    root = logging.getLogger()
    # h = logging.handlers.RotatingFileHandler('mptest.log', 'a', 30000, 3)
    h = logging.FileHandler('multi.log', 'a')
    f = logging.Formatter('%(asctime)s %(processName)-10s %(name)s %(levelname)-8s %(message)s')
    h.setFormatter(f)
    root.addHandler(h)
    h2 = logging.StreamHandler()
    f2 = logging.Formatter('%(levelname)s\t%(asctime)s\t%(processName)s\t%(name)s\t%(message)s')
    h2.setFormatter(f2)
    root.addHandler(h2)
    root.setLevel(logging.DEBUG)


# This is the listener process top-level loop: wait for logging events
# (LogRecords)on the queue and handle them, quit when you get a None for a

# LogRecord.
def listener_process(queue, configurer):
    configurer()
    while True:
        try:
            record = queue.get()
            if record is None:  # We send this as a sentinel to tell the listener to quit.
                break
            logger = logging.getLogger(record.name)
            logger.handle(record)  # No level or filter logic applied - just do it!
        except Exception:
            import sys, traceback
            print('Whoops! Problem:', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

# Arrays used for random selections in this demo


# LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING,
#           logging.ERROR, logging.CRITICAL]
#
# LOGGERS = ['a.b.c', 'd.e.f']
#
# MESSAGES = [
#     'Random message #1',
#     'Random message #2',
#     'Random message #3',
# ]


# The worker configuration is done at the start of the worker process run.
# Note that on Windows you can't rely on fork semantics, so each process
# will run the logging configuration code when it starts.
def worker_configurer(queue):
    h = logging.handlers.QueueHandler(queue)  # Just the one handler needed
    root = logging.getLogger()
    root.info('-------------------')
    root.info(root.handlers)
    root.info(':::::::::::::::::::')
    root.addHandler(h)
    # send all messages, for demo; no other level or filter logic applied.
    root.setLevel(logging.DEBUG)


# This is the worker process top-level loop, which just logs ten events with
# random intervening delays before terminating.
# The print messages are just so you know it's doing something!
# def worker_process(queue, configurer):
#     configurer(queue)
#     name = multiprocessing.current_process().name
#     print('Worker started: %s' % name)
#     for i in range(10):
#         time.sleep(random())
#         logger = logging.getLogger(choice(LOGGERS))
#         level = choice(LEVELS)
#         message = choice(MESSAGES)
#         logger.log(level, message)
#     print('Worker finished: %s' % name)


# Here's where the demo gets orchestrated. Create the queue, create and start
# the listener, create ten workers and start them, wait for them to finish,
# then send a None to the queue to tell the listener to finish.
def main():
    queue = multiprocessing.Queue(-1)
    listener = multiprocessing.Process(target=listener_process,
                                       args=(queue, listener_configurer))
    listener.start()
    # listener.join()
    # logger = logging.getLogger()
    # logger.setLevel(logging.DEBUG)
    # logger.info('Demonstration how to log from two different processes')
    # workers = []
    # for i in range(10):
    #     worker = multiprocessing.Process(target=worker_process,
    #                                      args=(queue, worker_configurer))
    #     workers.append(worker)
    #     worker.start()
    # for w in workers:
    #     w.join()
    #worker_configurer(queue)
    logger = logging.getLogger()
    logger.info('************************************1***************************************')
    from parallel_execution import sketch_multiprocess
    ccs, pool_name = sketch_multiprocess.prep_envi(queue=queue, configurer=worker_configurer)
    from parallel_execution import t1
    from parallel_execution import t2

    def create_and_start_process_1_1(ccs, pool_name, queue, configurer):
        event = multiprocessing.Event()
        one = t1.ExampleOne(do_verification=False)
        process = multiprocessing.Process(target=one.step_1,
                                          name='process_1_1',
                                          kwargs={'ccs': ccs,
                                                  'pool_name': pool_name,
                                                  'queue': queue,
                                                  'configurer': configurer,
                                                  'event': event})
        process.start()
        print('PID of the process {}: {}'.format(process.pid, process.name))
        return process, event

    logger.info('************************************2***************************************')

    def create_and_start_process_1_2(ccs, pool_name, queue, configurer):
        event = multiprocessing.Event()
        one = t1.ExampleOne(do_verification=False)
        process = multiprocessing.Process(target=one.step_2,
                                          name='process_1_2',
                                          kwargs={'ccs': ccs,
                                                  'pool_name': pool_name,
                                                  'queue': queue,
                                                  'configurer': configurer,
                                                  'event': event})
        process.start()
        print('PID of the process {}: {}'.format(process.pid, process.name))
        return process, event

    def create_and_start_process_1_3(ccs, pool_name, queue, configurer):
        event = multiprocessing.Event()
        one = t1.ExampleOne(do_verification=False)
        process = multiprocessing.Process(target=one.step_3,
                                          name='process_1_3',
                                          kwargs={'ccs': ccs,
                                                  'pool_name': pool_name,
                                                  'queue': queue,
                                                  'configurer': configurer,
                                                  'event': event})
        process.start()
        print('PID of the process {}: {}'.format(process.pid, process.name))
        return process, event

    def create_and_start_process_2_1(ccs, pool_name, queue, configurer):
        event = multiprocessing.Event()
        two = t2.ExampleTwo(do_verification=False)
        process = multiprocessing.Process(target=two.step_1,
                                          name='process_2_1',
                                          kwargs={'ccs': ccs,
                                                  'pool_name': pool_name,
                                                  'queue': queue,
                                                  'configurer': configurer,
                                                  'event': event})
        process.start()
        print('PID of the process {}: {}'.format(process.pid, process.name))
        return process, event

    logger.info('Start process 1_1')
    p1_1, p1_1_evt = create_and_start_process_1_1(ccs, pool_name, queue, worker_configurer)
    p1_1.join()
    logger.info('**************************************3*************************************')
    logger.info('Start process 1_2 and 2_1')
    p1_2, p1_2_evt = create_and_start_process_1_2(ccs, pool_name, queue, worker_configurer)
    p2_1, p2_1_evt = create_and_start_process_2_1(ccs, pool_name, queue, worker_configurer)
    p1_2.join()

    logger.info('Start process 1_3')
    p1_3, p1_3_evt = create_and_start_process_1_3(ccs, pool_name, queue, worker_configurer)
    p1_3.join()

    logger.warning('Setting event for p2_1')
    p2_1_evt.set()
    p2_1.join()

    queue.put_nowait(None)
    listener.join()


if __name__ == '__main__':
    main()
