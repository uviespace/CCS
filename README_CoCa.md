# CcsUvie
UVIE CCS configured for CoCa

Find the original repository here: https://gitlab.phaidra.org/mecinam2/CCS.git

## Installation
Please check the original installation steps.

Following you can find the steps used to install CCS on **Ubuntu**.

- git clone repository
- sudo apt install make
- sudo apt install libgtk-3-dev
- sudo apt install libgtksourceview-3.0-1
- install pip https://pip.pypa.io/en/stable/installation/
- sudo apt install python3.10-venv
- sudo apt-get install python3-dev
- sudo apt-get install libmysqlclient-dev
- sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtksource-3.0
- sudo apt install python-dbus-dev
- in contrast to the readme, I use my already installed mysql version (instead of using mariadb)
  * login to mysql (e.g. sudo mysql -u root)
  * CREATE USER 'ccs'@'localhost' IDENTIFIED BY 'Aik4eeya';
  * GRANT ALL PRIVILEGES ON * . * TO 'ccs'@'localhost';
  * FLUSH PRIVILEGES;
  * exit;
- python3 -m venv ./venv --system-site-packages
- source ./venv/bin/activate
- pip install -r requirements.txt
- configure database section in egse.cfg file:
  * line 14: user = ccs
  * line 16: password = Aik4eeya
  * also have a look into the paths, especially line 5 obsw
  * change line 11: COMETINTERCEPTOR
- make confignator
- make databases
- setup database with following steps:
  * change line 17 in egse.cfs to real mib-schema (e.g. mib_schema_coca)
  * import a set of SCOS2000 MIB files (e.g. ./Ccs/tools/import_mib.py './CoCa/mib_tables/mib_dat_exports/' 'mib_schema_coca' 'ccs')
  * ./Ccs/tools/import_mib.py 'path_to_MIB_file_directory' 'mib-schema-from-line-17-egse.cfs' 'db_user'
  * script will then ask for db password
- start CCS: ./start_ccs
- start TST: ./start_tst

## MIB Table Schema
The mib table import script uses the file [Ccs/tools/scos2000db.json](Ccs/tools/scos2000db.json)

If the project does not use the normal SCOS2000 schema, a change of
this file may be required.

## Scripting
The CCS Editor can be started with `./start_css`.

Within this editor scrips can be created / run. The default script
`connection_setup.py` implements a basic connection setup.

```python
# Basic connection setup to IASW sim via PLM SW sim

### Poolmanager ###
cfl.start_pmgr()

# PLM connection
cfl.connect('LIVE', '', 5570, protocol='PUS')
cfl.connect_tc('LIVE', '', 5571, protocol='PUS')

### Poolviewer ###
cfl.start_pv()

#! CCS.BREAKPOINT
### Monitor ###
cfl.start_monitor('LIVE')
```
It will do:

- starts the poolmanager
- creates an up and down connection (to localhost port 5570/5571)
- starts the poolviewer
- starts the monitor

(The script is stored under [Ccs/scripts](Ccs/scripts). The
`pool_name` is `LIVE`.)

If there is a need to **stop a running scipt** (e.g. a script sending telecommands in an endless loop) this can be done with CTRL+SHIFT+C.

For tests, you can find a **dummy socket client** under
[CoCa/test_scripts/dummy_socket.py](CoCa/test_scripts/dummy_socket.py)
it will just print out all binary commands sent to it.

## Scripting Tips
Tests are often controlled by a script. This section explains how to perform useful tasks from a script.

### Accessing Current TM Time and Display Row (GitHub Issue 14)
During testing, incoming TM Packets are displayed in the PoolViewer. Each packet is displayed in a dedicated row. The row contains, among other things, a Row Number (first item in the row) and the TM Packet Time-Stamp.

To access packets in a TM pool, there is the general-purpose command `cfl.get_pool_rows(<pool_name>)`. It returns a  `Query` object that supports interaction with the rows in the _tm_ table of the _xxx_data_storage_ schema. This class provides a number of useful methods. For example, to fetch a list of `DbTelemetry` objects, each representing a row in the queried pool, type

`cfl.get_pool_rows(<pool_name>).all()`

The `DbTelemetry` class in turn provides direct access to the properties of the individual rows, which hold the values that are also displayed in the PoolViewer columns. Exemplarily, `cfl.get_pool_rows("LIVE").all()[10].timestamp` will return the timestamp of the 11th packet in the pool _LIVE_.

The `Query` also allows very efficient filtering of rows by column values before the data are actually fetched, e.g., to obtain only TM packets of service type 5:

`cfl.get_pool_rows("LIVE").filter(cfl.DbTelemetry.stc==5).all()`

or only rows starting from index 100:

`cfl.get_pool_rows("LIVE").filter(cfl.DbTelemetry.idx>=100).all()`

In case of large pools it is highly recommended to filter the Query adequately before fetching the actual data (i.e., executing the `.all()` call or iterating through the Query instance), since instantiating a large number of rows as `DbTelemtery` objects takes a while.

With that in mind, the best way of getting the row index (or, analogously, any other property) of the last packet received will be as follows:

`cfl.get_pool_rows("LIVE").order_by(cfl.DbTelemetry.idx.desc()).first().idx` 

The `.raw` property will return the full packet as a byte-string. This is useful if there is a need to parse the TM packet:

```
tmPckt = cfl.get_pool_rows("LIVE").order_by(cfl.DbTelemetry.idx.desc()).first().raw
tmPcktParsed = cfl.Tmdata(tmPckt)
``` 

Here `tmPcktParsed` is a pair with (i starts from zero):

- `tmPcktParsed[0]` is a list of the TM packet parameters and their values
- `tmPcktParsed[0][i][0]` is the value of the i-th parameter in the TM packet 
- `tmPcktParsed[0][i][2]` is the descriptive name of the i-th parameter in the TM packet
- `tmPcktParsed[1]` is the descriptive name of the TM packet

Finally, to simply get the timestamp of the last received TM packet there is also the convenience function `cfl.get_last_pckt_time(pool_name=<pool_name>, string=True)`, which returns the time as a string or float, depending on the value of the`string` argument.

### Accessing TM Parameters (GitHub Issue 14)
If there is a need to access a specific parameter from a fixed-length TM packet, function `cfl.get_param_values` can be used/. Its most relevant parameters are:

- `param="AdcTemp"` name (description) of the parameter as defined in the MIB (PCF_DESCR)
- `hk="IASWHK_Essential"` description of the containing TM packet as per MIB (PID_DESCR)
- `pool_name="LIVE"` pool to query
- `last=4` the most recent 4 values of the parameters are retrieved

For instance:

`x = cfl.get_param_values(param='HB_TOGGLE', hk='TM_HB_REP', pool_name='LIVE', last=4)`

Variable x is a pair with 

- `x[0][0]` is an array of size 4 holding the time-stamps for the 4 requested parameter values
- `x[0][1]` is an array of size 4 holding the 4 requested parameter values
- `x[1]` is a pair holding the name of the parameter name and its unit of measure

In case of text-calibrated parameters it is necessary to set `mk_array=False` to get the calibrated values as strings, otherwise their raw numerical values will be returned. For instance:

`cfl.get_param_values(param='HB_MASW_MODE', hk='TM_HB_REP', pool_name='LIVE', last=4, mk_array=False)`


## Parameter Monitoring
A Monitoring Module is available which can be started from the Editor Terminal: `acfl.start_monitor('LIVE', parameter_set='states')`. Alternatively, it can also be started from a terminal: `python monitor.py <POOLNAME> <PARAMSET>`.

The parameter sets are stored in the `Ccs/ccs_main_config,cfg` under the [ccs-monitor_parameter_sets] section.
If you want to delete a set, you have to remove the corresponding entry in that file, there is no GUI interface for this yet.

On the left-hand side of the monitor display you have counters that monitor the number of event reports received in the pool (LOW, MID, HIGH). The reset button sets the colour of these counters to black such that a change in counts can again be highlighted by switching to red.


## Troubleshooting

### Add Additional Logs to CCS Log Window

CCS runs in different processes, to add additional logs to the CCS log
window (tab in the CCS Editor). Add following lines:

```python
import logging
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
logging.warning('...')
```

### Change Default Log Level

To enable more extensive logging, set the `level` option in
[Ccs/ccs_main_config.cfg](Ccs/ccs_main_config.cfg)

[comment]: # (discussion on github https://github.com/mmecina/CCS/issues/4#issuecomment-1922284468)

```ini
[ccs-logging]
log-dir = ${paths:base}/logs
level = DEBUG
max_logs = 30
```

### Make Exceptions Visible
If there is an exception in a process running in the background, the process fails but the user does not notice it. In order to investigate such problems, one can run the process not as a stand-alone process, but in the CCS Editor terminal. For instance, if one suspects an error in the Poolviewer, one can start it from the CCS Editor by executing

```python
cfl.start_pv(console=True)
```

In this way, unhandled exceptions will be seen in the CCS console. 

### Use of the Python Debugger
If there is a need to run the python debugger, most modules can also be run by executing the respective Python files directly which allows the debugger to be accessed normally. Examples of modules which can be started in this way include:
- The PoolViewer is started by running `./Ccs/poolview_sql.py`
- The TestSpecificationTool is started by running `./Tst/tst/tst.py`
