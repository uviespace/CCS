import sys

from gi.repository import Gio, Gtk, GObject

'''
main_loop = GObject.MainLoop()

class MessageListener(Gio.DBusInterfaceSkeleton):
    """
    <node>
        <interface name='com.moeslinger.example.interface'>
            <method name='ConnectionCheck'>
                <arg type='s' name='response' direction='out'/>
            </method>
        </interface>
    </node>
    """

    def __init__(self):
        introspection_xml ="""
    <node>
        <interface name='com.moeslinger.example.interface'>
            <method name='ConnectionCheck'>
                <arg type='s' name='response' direction='out'/>
            </method>
        </interface>
    </node>
    """
        #introspection_xml = Gio.DBusInterfaceSkeleton(introspection_xml)
        id = Gio.bus_own_name(Gio.BusType.SESSION,
                            'com.moeslinger.example',
                            Gio.BusNameOwnerFlags.NONE, self.on_name_aquired ,None)

        introspection_data = Gio.DBusNodeInfo.new_for_xml(introspection_xml)
        self.introspection_data = introspection_data
        #GDbus_id = Gio.DBusConnection.new(Gio.BusType.SESSION, None, Gio.BusNameOwnerFlags.NONE, None,None,None,None)
        #Gio.DBusConnection.register_object(GDbus_id, '/com/moeslinger/example/path', introspection_data,None,None,None)

    def on_name_aquired(self,connection, name):
        Gio.DBusConnection.register_object(connection, '/com/moeslinger/example/path',self.introspection_data, self.handling_method_calls)

    def handling_method_calls(self,method_name):
        if method_name == 'ConnectionCheck':
            self.ConnectionCheck()

    def ConnectionCheck(self, argument =None):
        connectivity = 'ConnectionWorked'
        if argument is not None:
            print(argument)
        else:
            print('Connection is ok')
        return connectivity


if __name__ == '__main__':
    MessageListener()

main_loop.run()
'''
xml="""
<node>
    <interface name='com.moeslinger.example.interface'>
        <method name='ConnectionCheck'>
            <arg type='s' name='response' direction='out'/>
        </method>
    </interface>
</node>
"""

import sys

from gi.repository import Gio, Gtk


class App(Gio.Application):

    def __init__(self):
        Gio.Application.__init__(self,
                                 application_id="org.gnome.example",
                                 flags=Gio.ApplicationFlags.FLAGS_NONE)
                                 # flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

        self.connect("activate", self.activateCb)
        #self.connect("command-line", self.my_argv)

    def xyzdo_command_line (self, args):
      # adopted from multiple examples do_command_line is needed any time
      # HANDLES_COMMAND_LINE is triggered, which can happen in multiple ways.
      # by default, it calls signals activate, which invokes some kind of main
      # loop with an appropriate context
      print("XYZ", args.get_arguments( ))
      # help(args)
      # help(line)
      # self.do_activate(self)
      self.activate( )
      return 0
      return Gio.Application.do_activate(self)

    def activateCb(self, app):
        print("ACTIVATED!")
        a=input()
        # sans GUI default loop taking over, there is nothing to do
        """
        many apps supply GUIs, and will launch windows in the "main" instance.
        What about internet of things apps, which need to export informatin
        over dbus/websocket and simply want to export data, maybe signals, and
        if lucky methods, on a bus?
        With a gui this works, and even registers on properly on d-feet.
        For now it's not clear how to launch managed objects purely as a
        library, and potentially export them on new threads as appropriate for
        library usage.
        It has something to do with iterating a MainLoop using MainContext's
        push_thread_default, but no documentation or examples makes this
        explicit.
        """
        """
        window = Gio.ApplicationWindow()
        app.add_window(window)
        window.show()
        """

    def do_local_command_line (self, args):
      print("XXX", self, args)
      # run any argparse here, including argcomplete?
      # Let Gio/Gio
      foo = Gio.Application.do_local_command_line(self, args[:1])
      # print foo
      ret = (True, None, 0) # allows dispatchin inner mainloop
      # ret = (False, None, 0) # continue invoking do_command_line logic, regardless of registered Flags!!
      # print foo == ret
      print(ret)
      return ret

if __name__ == '__main__':
    app = App()
    # this does not work either...
    try:
      app.run(sys.argv)
    except KeyboardInterrupt as e:
      print("Quitting")
      app.quit( )
sys.exit(0)
