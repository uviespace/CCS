#!/usr/bin/python3
import logging
import dbus
import time
import sys
import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
sys.path.append(confignator.get_option('paths', 'tst'))
import ccs_function_lib as cfl

module_logger = logging.getLogger(__name__)
hdlr = logging.StreamHandler()
module_logger.setLevel(logging.DEBUG)
frmt = logging.Formatter(fmt='%(levelname)s\t%(asctime)s\tlogger: %(name)s:\t%(message)s')
hdlr.setFormatter(frmt)
module_logger.addHandler(hdlr)


def connect_to_app(name, logger=module_logger):
    app = False
    k = 0
    while k < 20:
        logger.debug('+++++++++++++++++ {} +++++++++++++++++'.format(k))
        logger.debug('Trying to connect to the {} via DBus.'.format(name))
        try:
            app = cfl.dbus_connection(name)
        except Exception as e:
            pass
            # logger.exception(e)
        if app is False:
            logger.debug('Failed to connect to the {} via DBus'.format(name))
            time.sleep(0.5)
        if app is not False:
            con_check = app.ConnectionCheck()
            if isinstance(con_check, dbus.String):
                logger.info('Successfully connected to the {} via DBus - {}'.format(name, con_check))
                break
        k += 1
    return app


def connect_to_editor(logger=module_logger):
    try:
        bus_name = confignator.get_option(section='dbus_names', option='editor')
        bus = dbus.SessionBus()
        editor = bus.get_object(bus_name, '/MessageListener')
        editor.ConnectionCheck()
    except dbus.exceptions.DBusException as dbe:
        logger.error('Could not connect to the editor application')
        logger.exception(dbe)
        return
    return editor


def connect_to_tst(logger=module_logger):
    try:
        bus_name = confignator.get_option('dbus_names', 'tst')
        obj_path = '/smile/egse/tst/editor/window/1'

        bus = dbus.SessionBus()
        obj = bus.get_object(bus_name=bus_name, object_path=obj_path)
        interface_actions = dbus.Interface(obj, 'org.gtk.Actions')
        actions = interface_actions.List()
        print('Available Actions:')
        for item in actions:
            print(item)
        print('closing the current page in Tst')
        interface_actions.Activate(actions[0], [], [])
    except dbus.exceptions.DBusException as dbe:
        logger.exception(dbe)


def connect_to_progress_viewer(logger=module_logger):
    bus_name = confignator.get_option('dbus_names', 'progress-view')
    obj_path = '/' + bus_name.replace('.', '/') + '/window/1'
    bus = dbus.SessionBus()
    obj = bus.get_object(bus_name=bus_name, object_path=obj_path)
    interface_actions = dbus.Interface(obj, 'org.gtk.Actions')
    actions = interface_actions.List()
    logger.debug('Available Actions for {}:'.format(bus_name))
    for item in actions:
        logger.debug('{}'.format(item))
    return interface_actions


if __name__ == '__main__':
    connect_to_tst()
    connect_to_editor()
    connect_to_progress_viewer()
