'''
Unit testing the DB API
'''
import datetime, time

from sqlalchemy.orm.session import Session

from .tm_db import scoped_session_maker, create_storage_db, DbTelemetryPool, DbTelemetry
from .config_db import telemetry_pool_table, telemetry_table


def add_example_data(sess: Session) -> None:
    '''Add some test data to the DB (used for tests)'''
    pool = DbTelemetryPool(pool_name='test-pool',
                           modification_time=time.time())
    sess.add(pool)
    sess.flush()

    for i in range(1000):
        tlm = DbTelemetry(
            pool_id=pool.iid, idx=i+1, is_tm=True, apid=1796, seq=203+i,
            len_7=42, stc=5, sst=241, destID=0, timestamp=1370+i,
            data=bytes.fromhex('deadbeefdeadc0deadeadbee'),
            raw=bytes.fromhex('deadbeefdeadc0deadeadbee'))
        sess.add(tlm)
    sess.commit()


def drop_tables():
    '''Drop the TM tables'''
    sess = scoped_session_maker('idb')
    try:
        for t in [telemetry_table, telemetry_pool_table]:
            sess.execute('drop table %s;' % t)
    except Exception as _:  # pragma: no cover pylint: disable=W0703 
        pass  # pragma: no cover


def test_tables_creation():
    '''Drop and create the tables from scratch, then load them with data'''
    drop_tables()
    sess = create_storage_db(protocol='PUS', force=True)
    add_example_data(sess)
    assert sess.query(DbTelemetry).count() == 1000
