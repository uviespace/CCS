import confignator

cfg = confignator.get_config()

user = cfg.get('database', 'user')
pw = cfg.get('database', 'password')
host = cfg.get('database', 'host')

# --------------- schema names ---------------
idb_schema_name = cfg.get('ccs-database', 'idb_schema')
storage_schema_name = '{}_data_storage'.format(cfg.get('ccs-database', 'project').lower())

# --------------- storage database tables ---------------
telemetry_pool_table = 'tm_pool'
telemetry_table = 'tm'

# --------------- database connection ---------------
mysql_connection_string = 'mysql://{}:{}@{}'.format(user, pw, host)
