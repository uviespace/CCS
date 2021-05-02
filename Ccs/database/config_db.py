# --------------- SMILE ---------------
idb_schema_name = 'mib_smile_sxi'
storage_schema_name = 'smile_data_storage'
# pus_storage_schema_name = 'rmap_data_storage'
# rmap_storage_schema_name = 'rmap_data_storage'
# feedata_storage_schema_name = 'fee_data_storage'

# --------------- CHEOPS ---------------
# idb_schema_name = 'dabys_mib_cheops_v2.30'
# idb_schema_name = 'dabys_mib_cheops'
# idb_schema_name = 'mib_sxi'
# idb_schema_name = 'dabys_mib_cheops_2.4'
# idb_schema_name = 'cheops_idb'  ##Dominik
# storage_schema_name = 'cheops_data_storage'  ## Dominik

# --------------- storage database tables ---------------
telemetry_pool_table = 'tm_pool'
telemetry_table = 'tm'

# --------------- database connection ---------------
# mysql_connection_string = 'mysql://egse:weltraummuell@localhost'
# mysql_connection_string = 'mysql://dabys_admin:123dabys_admin@localhost/' + idb_schema_name
#mysql_connection_string = 'mysql://sxi:whysoserious@localhost'
# mysql_connection_string = 'mysql://root:spacewiki@localhost'
# mysql_connection_string = 'mysql://stefan:stefan@localhost'
mysql_connection_string = 'mysql://egse:weltraummuell@localhost'
