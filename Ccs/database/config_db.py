import confignator

cfg = confignator.get_config()

user = cfg.get('database', 'user')
pw = cfg.get('database', 'password')

# --------------- SMILE ---------------
# idb_schema_name = 'mib_smile_sxi'
idb_schema_name = cfg.get('ccs-database', 'idb_schema')
# storage_schema_name = 'smile_data_storage'
storage_schema_name = '{}_data_storage'.format(cfg.get('ccs-database', 'project').lower())

# --------------- CHEOPS ---------------
# idb_schema_name = 'dabys_mib_cheops'

# --------------- storage database tables ---------------
telemetry_pool_table = 'tm_pool'
telemetry_table = 'tm'

# --------------- database connection ---------------
mysql_connection_string = 'mysql://{}:{}@localhost'.format(user, pw)
