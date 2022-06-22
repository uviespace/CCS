#This file is used to set up a D-Bus
import dbus
import dbus.service
import sys
import subprocess
#import confignator
import ccs_function_lib as cfl
import os



#Set up two Methodes to excess over a given dbus name
class MessageListener(dbus.service.Object):
    def __init__(self, win, Bus_Name, *args):
        project = None
        # Get project title from arguments
        for arg in args:
            if not arg.startswith('/') and arg.startswith('-') and arg.endswith('-'):
                project = arg[1:-1]

        self.bus = dbus.SessionBus()
        self.win = win

        Bus_Name += str(1)

        #Check if the Bus name already exists and increase the number if it does
        counting = 1
        check = True
        while check == True:
            counting += 1
            for service in dbus.SessionBus().list_names():
                if service == Bus_Name:
                    Bus_Name = Bus_Name[:-1] + str(counting)
                    check = True
                    break
                else:
                    check = False

        #Set up the bus
        self.Bus_Name = Bus_Name
        self.name = dbus.service.BusName(self.Bus_Name, bus=self.bus)
        super().__init__(self.name, '/MessageListener')
        self.win = win
        #### This will be a series of functions to let the user use more than one 'instance' of the CCS running on the
        # same machine,
        # Variabel project is the name of the group of application working together
        if not project:
            project = self.win.cfg['ccs-database']['project']

        self.win.main_instance = project    # Variable in each application to tell the group name

        # This exception is necessary for the Poolmanager since most of the time a GUI does not exist
        try:
            self.win.set_title(str(project) + ': ' + str(self.win.get_title()) + ' ' + str(counting-1))
        except:
            # Looks like an odd title name but is reshaped in pus_datapool.py
            self.win.windowname = str(project) + ': @ ' + str(counting-1)
        ###

        # Tell the terminal that a bus has been set up, this function has to exist in every file
        self.win.connect_to_all(Bus_Name, counting - 1)

        # Start the Logging TCP-Server, the check if it is already setup is in log_server.py
        import log_server
        log_server_path = log_server.__file__
        os.system('nohup python3 ' + str(log_server_path) + ' >/dev/null 2>&1 &')
        #subprocess.Popen(['python3', log_server_path])

    # Return all available methods
    @dbus.service.method('com.communication.interface')
    def show_functions(self, argument=None):
        method_list_former = dir(self.win)
        method_list = []
        for method in method_list_former:
            if method.startswith('__'):
                pass
            elif argument and not argument in method:
                pass
            else:
                method_list.append(method)

        return method_list

    # Check if there is a connection
    @dbus.service.method('com.communication.interface')
    def ConnectionCheck(self, argument=None):
        connectivity = 'ConnectionWorked'
        if argument is not None:
            print(argument)
            return argument
        else:
            print('Connection is ok')
        return connectivity

    # This function is used in the logging file to check if a process is still running
    # It is outdated and no longer used by the Logging process
    @dbus.service.method('com.communication.interface')
    def LoggingCheck(self, argument=None):
        if argument is not None:
            print(argument)
        return

    #This makes one use all function given in the used file for the given instance (win variable in __init__ function)
    @dbus.service.method('com.communication.interface', byte_arrays=True)
    def Functions(self, function_name, *args):

        if len(args) > 0 and args[0] == 'user_console_is_True':
            user_console = True
            args = args[1:]

            args, kwargs = self.check_for_kwargs(args)

            new_data = dict()
            for key in kwargs.keys():
                new_data[key] = self.dbus_to_python(kwargs[key], user_console)
            kwargs = new_data
            args = (self.dbus_to_python(value, user_console=user_console) for value in args)

        else:
            user_console = False
            args, kwargs = self.check_for_kwargs(args)

        method_to_call = getattr(self.win, function_name)
        try:
            result = method_to_call(*args, **kwargs)
        except Exception as e:
            result = str(e)
        result = self.python_to_dbus(result, user_console=user_console)
        return result

    # This makes one use all Variables given in the used file for the given instance (win variable in __init__ function)
    @dbus.service.method('com.communication.interface')
    def Variables(self, variable_name, *args):
        if len(args) > 0 and args[0] == 'user_console_is_True':
            user_console = True
            args = args[1:]

        else:
            user_console = False

        if len(args) > 1:
            print('Please give exactly 1 argument which the variable should hold')
        elif not args:
            variable = getattr(self.win, variable_name)
            '''if variable:
                return variable
            else:
                return'''
            variable = self.python_to_dbus(variable, user_console=user_console)
            return variable
        else:
            arg = self.dbus_to_python(args[0], user_console=user_console)
            setattr(self.win, variable_name, arg)
        return

    # This makes one use all dictionaries given in the used file for the given instance (win variable in __init__ function)
    @dbus.service.method('com.communication.interface')
    def Dictionaries(self, dict_name, *args):
        if len(args) > 0 and args[0] == 'user_console_is_True':
            user_console = True
            args = args[1:]

        else:
            user_console = False

        dict_to_call = getattr(self.win, dict_name)
        args = [self.dbus_to_python(value, user_console=user_console) for value in args]
        # Return the dictonary
        if not args:
            return self.python_to_dbus(dict_to_call, user_console=user_console)
        # Return the value of the given key of the dictionary
        elif len(args) == 1:
            result = dict_to_call[args[0]]
            return self.python_to_dbus(result, user_console=user_console)
        # Return the value of the given keys list, nearly never used
        elif len(args) == 3 and args[2] is True:
            result = dict_to_call[args[0]][args[1]]
            return self.python_to_dbus(result, user_console=user_console)
        # Change the value of the given keys list entry, nearly never used
        elif len(args) == 4 and args[3] is True:
            dict_to_call[args[0]][args[1]] = args[2]
            return
        else:
            count = 0
            try:
                if len(args)%2 != 0:
                    raise KeyError
                while count < len(args):
                    dict_to_call[args[count]] = args[count+1]
                    count += 2
            except:
                print('Please give a valid number of arguments')
            return

    '''
    # Check if project name already exists and change it to name2, name3 if needed
    def check_project_name(self, project):
        cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))

        count = 1
        repeat = True
        while repeat:
            repeat = False
            our_con = []
            for service in dbus.SessionBus().list_names():
                if service.startswith('com'):
                    our_con.append(service)

            for app in our_con:
                if app[:-1] in cfg['ccs-dbus_names']:
                    conn = cfl.dbus_connection(app.split('.')[1], app[-1])
                    if project == conn.Variables('main_instance'):
                        repeat = True
                        
            if not repeat:
                project += str(count)
            count += 1
        
        return project
    '''

    # This is just a workaround function for a problem which one has with dbus, It does not support keyword arguments!!
    # Therefore all arguments and keyword argument are sent via *args, put them in a dictionary and name the first key:
    # 'kwargs' The rest of the dictionary will be interpreted like keyword arguments
    # This is not a very pretty solution but it is working
    def check_for_kwargs(self, arguments):
        '''
        args = list(arguments)
        kwargs = {}
        for arg in arguments:
            if isinstance(arg, dict):
                if arg.get('kwargs'):
                    del arg['kwargs']
                    kwargs = arg
                    args.remove(arg)
        '''
        args = list(arguments)
        kwargs = {}
        for arg in arguments:
            if isinstance(arg, dict):
                if arg.get('kwargs'):
                    kwargs = arg['kwargs']
                    del arg['kwargs']
                    #kwargs = arg
                    args.remove(arg)


        '''
        breaklist = list(arguments)
        for arg in arguments:
            if arg == 'nokwargsincluded': #If I do not want to check for kwargs do this
                breaklist.remove('nokwargsincluded')
                breaklist = tuple(breaklist)
                return breaklist, {}
            if isinstance(arg,str):
                if '=' in arg:
                    if ' =' in arg:
                        newarg = arg.split()
                        newarg[-1] = newarg[-1].split(' =')
                    elif '= ' in arg:
                        newarg = arg.split()
                        newarg[0] = newarg[0].split('=')
                    elif ' = ' in arg:
                        newarg = arg.split()
                    else:
                        newarg = arg.split()
                        newarg = newarg.split('=')

                    argdict = dict([(newarg[0], newarg[-1])])
                    kwargs.update(argdict)
                else:
                    args.append(arg)
            else:
                args.append(arg)
        args = tuple(args)
        return args, kwargs
        '''
        arguments = tuple(args)
        return arguments, kwargs

    def dbus_to_python( self, data, user_console=False):
        """
        Convets dbus Types to Python Types
        @param data: Dbus Type variables or containers
        @param user_console: Flag to check for NoneType arguments
        @return: Same data as python variables or containers
        """
        # NoneType string is transformed to a python None type
        if user_console and data == 'NoneType':
            data = None
        elif isinstance(data, dbus.String):
            data = str(data)
        elif isinstance(data, dbus.Boolean):
            data = bool(data)
        elif isinstance(data, (dbus.Int16, dbus.UInt16, dbus.Int32, dbus.UInt32, dbus.Int64, dbus.UInt64)):
            data = int(data)
        elif isinstance(data, dbus.Double):
            data = float(data)
        elif isinstance(data, dbus.Array):
            data = [self.dbus_to_python(value, user_console) for value in data]
        elif isinstance(data, dbus.Dictionary):
            new_data = dict()
            for key in data.keys():
                new_data[str(key)] = self.dbus_to_python(data[key], user_console)
            data = new_data
        elif isinstance(data, dbus.ByteArray):
            data = bytes(data)
        elif isinstance(data, dbus.Struct):
            data = (self.dbus_to_python(value, user_console) for value in data)
        return data

    def python_to_dbus(self, data, user_console=False):
        """
        Convets Python Types to Dbus Types, only containers, since 'normal' data types are converted automatically by dbus
        @param data: Dbus Type variables or containers
        @param user_console: Flag to check for NoneType arguments
        @return: Same data for python variables, same data for container types as dbus containers
        """

        if user_console and data is None:
            data = dbus.String('NoneType')
        elif isinstance(data, list):
            data = dbus.Array([self.python_to_dbus(value, user_console) for value in data], signature='v')
        elif isinstance(data, dict):
            data = dbus.Dictionary(data, signature='sv')
            for key in data.keys():
                data[key] = self.python_to_dbus(data[key], user_console)
        elif isinstance(data, tuple):
            data = dbus.Struct([self.python_to_dbus(value, user_console) for value in data], signature='v')
        elif isinstance(data, (int, str, float, bool, bytes, bytearray)):
            pass
        else:
            self.win.logger.info("Object of type " + str(type(data)) + " can probably not be sent via dbus")
        return data


'''
################### PyDBus #####################
from pydbus import SessionBus

class Dbus():
    def __init__(self, win, Bus_name):
        bus = SessionBus()
        bus.publish(Bus_name, MessageListenerpy(win))

class MessageListenerpy(object):
    """
    	<node>
    		<interface name='com.editor.communication.interface'>
    			<method name='ConnectionCheck'>
    				<arg type='s' name='response' direction='out'/>
    			</method>
    			<method name='Function_Library'>
    			    <arg type='s' name='a' direction='in'/>
    			    <arg type='s' name='b' direction='in'/>
    				<arg type='s' name='response' direction='out'/>
    			</method>
    		</interface>
    	</node>
    """

    def __init__(self, win):
        self.win = win

    #@dbus.service.method('com.editor.communication')
    def ConnectionCheck(self, argument=None):
        connectivity = 'ConnectionWorked'
        if argument is not None:
            print(argument)
        else:
            print('Connection is ok')
        return connectivity

    #This makes one use all function given in the used file for the given instance (win variable in __init__ function)
    #@dbus.service.method('com.editor.communication', in_signature='s')
    def Function_Library(self, function_name, *args, **kwargs):
        connectivity = 'ConnectionWorked'

        method_to_call = getattr(self.win, function_name)
        result = method_to_call(*args, **kwargs)

        if isinstance(result, (str, int, float)):
            return result
        else:
            return connectivity

'''