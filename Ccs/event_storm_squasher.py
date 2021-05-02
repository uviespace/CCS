import time
import logging
from functools import wraps
from typing import Callable, List, Tuple, Any  # NOQA pylint: disable=unused-import

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib  # NOQA


def delayed(milliseconds: int) -> Callable[[Callable], Callable]:
    """
    This decorator 'squashes' bursts of calls to the decorated
    function with inter-arrival times less than 'milliseconds'
    into a single one - the last one that was ever made. To do
    that, it keeps track (via time.time() ) of the time each
    call is made, queues a closure-d version inside "delayed_calls",
    and only executes the last one AFTER the provided milliseconds
    have passed and no new call has arrived.

    This decorator is used to handle the unexplained (as of yet)
    bursts of events sent by the CHEOPS GTK widgets.

    Note that it can only be used for functions that DONT return
    anything - since the 'squashing' means that they will be
    executed in the context of a timer (no returning of anything
    to the caller).
    """
    def real_decorator(f: Callable) -> Callable:
        timer_handle = []  # type: List[Any]
        delayed_calls = []  # type: List[Tuple[float, Callable]]

        def event_squasher() -> bool:
            # logging.debug("Timer fired!...")
            if delayed_calls:
                now = time.time()
                last_call = delayed_calls[-1]
                if now - last_call[0] > milliseconds/1000.:
                    delayed_calls.clear()
                    # logging.debug("Removing timer...")
                    GLib.source_remove(timer_handle[0])
                    timer_handle.clear()
                    last_call[1]()
                    return False  # All done, timer done
            return True  # Not done yet, ask timer to re-fire

        @wraps(f)
        def wrapper_func(*args: Any, **kwargs: Any) -> None:

            def closured_func() -> None:
                """
                The 'closured' version of the call - i.e. kept in
                a form that can be queued inside delayed_calls 
                and called with a simple '()' appended (no args).
                """
                f(*args, **kwargs)

            delayed_calls.append((time.time(), closured_func))
            if not timer_handle:
                # logging.debug("Setting up timer...")
                timer_handle.append(
                    GLib.timeout_add(milliseconds, event_squasher))

        return wrapper_func
    return real_decorator
