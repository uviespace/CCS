
# This File gives a basic overview on the most important Functions to use the CCS

# If it is not already running start the ccs.py file, this file will appear there automatically

# The program now running is called the Editor

# The variable 'cfl', which is available in the Editor and in the Python Console in the Editor, refers to the
# CCS-Function-Library which contains most of the Functions. Furthermore several other applications can be opened.
# These will perform different task and should be, for basic usage, completely controllable via the respective GUIs.

# If one wants to communicate with these individual tasks 'D-Bus' can be used. That is pretty simple:
# A connection to these applications should automatically be made and the variable to call is displayed in the Console
# below. However if the connection should not be made automatically do this:
con = cfl.dbus_connection('application_name')
# 'application_name' has to be changed to the lowercase name of one of the applications described below.

# There are two main way to use dbus in the CCS:
# The first one is more user friendly and handles some problems with dbus automatically, but it can lead to problems for
# very specific requirements, It is the preferred way for most CCS users
# The second one is using the Dbus "language" directly, which is mostly recommended for Developers

### First DBus Way
# Functions can be used like this:
reply = cfl.Functions('dbus_con', 'function_to_call', 'argument1', 'argument2', keyword='value')
# dbus_con is the variable of the connection to a CCS_application which for the poolviewer would be 'pv1'
# So to call the poolviewer use (of course the Poolviewer has to be running):
reply = cfl.Functions(pv1, 'function_to_call', 'argument1')

# The value of a variable will can be accessed like this:
reply = cfl.Variables('dbus_con', 'variable_name')
# To change a variables value it is possible to pass along a second argument that it should hold
reply = cfl.Variables('dbus_con', 'variable_name', 'new_value')

# Dictionarys can be used in multiple ways, show the entire dictionary, show a value or change a value of a Dictionary
# Show entire Dictionary:
reply = cfl.Dictionaries('dbus_con', 'dictionary_name')
# Show only one Value of the Dictionary:
reply = cfl.Dictionaries('dbus_con', 'dictionary_name', 'key_to_the_value')
# Change a Variable in the Dictionary:
reply = cfl.Dictionaries('dbus_con', 'dictionary_name', 'key_to_the_value', 'new_value')

# And to check if a connection is working use:
cfl.ConnectionCheck('dbus_con')


### Second DBus Way:
# Functions can be used via dbus like this:
reply = con.Functions('function_to_call', 'argument1', 'argument2')

# Here we get to a problem with dbus, it does not support keyword arguments, only normal arguments. If one wants to use
# a keyword argument simply use the implemented function kwargs, with the dictionary containing the keywords passed
# along, Just like this
reply = con.Functions('function_to_call', 'argument', kwargs({'keyword1': 'value1', 'keyword2': 'value2'}))

# If keywords want to be used outside of the CCS console, there is a little more typing involved, it is necessary to
# pass along many things dbus needs:
reply = con.Functions('function_to_call', 'argument', {'kwargs': dbus.Dictionary({'keyword1': 'value1', 'keyword2': 'value2'}, signature='sv')})

# Values of all Variables can be accessed like this:
value = con.Variabĺes('variable')

# The other ways to use Variables and Dictionaries can analog be used as well

# If one wants to check if a Application is running:
run = cfl.is_open('application_name') # Returns True if running, False if not


### Editor ###

# This is the application which will be started if one opens the ccs.py file. It is somewhat of the main application
# in this project. It is basically used to write, load and edit scripts which control the CCS. These scripts can be run
# with the blue arrows in the to-left corner. All of the commands will be run by the basic Python Shell in the lower
# part of this application. Since the Terminal is running in the Editor GUI and is independent of it is possible to
# communicate with the editor via dbus:
editor.Functions('somefunctiontocall')

# An additonal editor can be started like this:
cfl.start_editor()


### Poolmanager ###

# The Poolmanager is responsible for storing and loading data from the Database and for the connection to the
# simulators. However in a lot of cases the Manager performs tasks in the background, therefore it can also be used
# without the GUI. It can be started with the command:
cfl.start_pmgr()

# To make a connection to the simulators two commands exist
# One to receive data:
pmgr.Functions('connect', 'pool_name', '127.0.0.1', 5570) # Pool_name, I.P. Adress, Port
# And one to send Telecomands:
ppp = pmgr.Functions('connect_tc', 'pool_name', '127.0.0.1', 5571) # Pool_name, I.P. Adress, Port


### Poolviewer ###

# Start the Poolviewer, since the Poolviewer is working very closely with the Poolmanager please start it as well,
# the used command is given above.
cfl.start_pv()

# The Viewer is mostly used to show the incoming packets and on the left side it will show the
# parameters which can be decoded. If a already saved pool should be loaded use:
pv.Functions('load_saved_pool', '/path/to/the/pool/poolname.tmpool')

# If a new 'live' pool is comming in from a simulator via the Poolmanager, tell the Viewer to show it:
pv.Functions('set_pool', pool_name)


### Monitor ###

# The Monitor can be used to check on some Parameters if they stay in there defined limits. To start use:
cfl.start_monitor()

# To specify the used Pool:
monitor.Functions('set_pool', '/path/to/the/pool/poolname.tmpool')

# Specify the monitored parameters via the 'Set_Parameters' Button in the Monitor


### Plotter ###

# The Plotter is used to show graphically the value of a parameter. It is started via:
cfl.start_plotter()

# Since this is a application to show the data graphically it is best to use via the GUI

###
# In every application in the top right corner a Button does exist with looks like the Logo of the University of Vienna.
# With this one can launch all application via any GUI. Furthermore the communication between multiple application
# instances can be managed which will be explained below.
###
#############
# Small Useful Tools

# Convert Dbus types to Python Types (often already done, but for some purposes this may be useful)
# Dbus returns Values as dbus.Types not as typical python type objects. For the machine it does not matter since each
# dbus.Type is a subclass of a typical python type, but for humans it is prettier to read if the types are changed. This
# Function can be used
cfl.dbus_to_python(data)
# data: some dbus type object
# return: The same data as typicall python types

# Show all available Functions
# Since it is not possible to use autocomplete of Functions if they should be called via dbus a function is implemented
# to show all available functions:
cfl.show_functions('dbus_con', 'Filter')
# dbus_con: A dbus connection
# Filter: String used as a filter for all functions

# To show all functions of the CFL simply use the python implemented function dir():
dir(cfl)

# For faster typing but with a worse looking output, simply use the dbus-connection to the module and type the command:
# For example for the Poolviewer:
pv.show_functions('Filter')


#############
# Multiple CCS projects

# It is also possible to run two completely independent CCS on the same machine. To do this simply start an application
# with one of the command listed above and add the name of the new project, in this format '-newname-', as an argument:
cfl.start_pmgr('-my_project_name-')
# Note that the project name has to be passed along whenever a new application is started (name is case sensitive)

# The project name for each application can be seen in the beginning of the GUI title


##############
# Multiple Instances of applications

# It is of course possible to work with more than one running application. To still manage which one should execute the
# commands given by another application it is possible to either manage them via the blue button in the top right corner
# or via the command line of course. For better understanding here is an example:
# If one wants to have two Poolviewers available and wants to add a Pool from the Poolmanager, by using the "Display"
# button, it will always be completely random which Poolviewer will display the Pool. To select which should be used,
# use the option 'Communication' in the UniVie Button in the top right corner. This will open a small GUI in which it
# can be easily seen which Application Instance is used at the moment and it can be changed as well.
# To only see which Instances are selected at the moment one can also use the commandline. Just use dbus an call one
# application, for example the Poolmanager:
cfl.Functions('get_communication')

# To change the communication with the command line use this command:
cfl.change_communication_func('main_instance', 'new_main', 'new_main_nbr', 'application', 'application_nbr')
## Necessary Variable:
# main_instance: the project name, which is displayed at the beginning of each Window title (case sensitive)
# new_main: the new application which should be called in the future
# new_main_nbr: the instance of the new application, shown in title of each Window
## Additional Variables, if None changes will apply to all applications of this project
# application: the application name for which should communicate to the new give instance
# apllication_nbr: instance of this application

# For example, this would lead to all applications in project SMILE communication primarily with Poolviewer 2
cfl.change_communication_func('SMILE', 'poolviewer', 2)

# Another example, this would make the poolmanger 1 communicate with the poolviewer 2 and show all pools there, but for
# all other apps in the project the main poolviewer would stay the same
cfl.change_communication_func('SMILE', 'poolviewer', 2, 'poolmanager', 1)

# The second example could also be achieved with dbus, call the poolmanager and change communication to poolviewer 2:
pmgr.Functions('change_communication', 'poolviewer', 2)
