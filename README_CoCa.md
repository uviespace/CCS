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

For tests, you can find a dummy socket client under
[CoCa/test_scripts/dummy_socket.py](CoCa/test_scripts/dummy_socket.py)
it will just print out all binary commands sent to it.

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

In this way, unhandled exceptions will be seen in the CCS console
