'''
This module provides Telemetry serialization and loading functionality.
'''
# pylint: disable=too-few-public-methods

import sys

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, Integer, Boolean, Unicode, Index, UniqueConstraint, ForeignKey, create_engine, engine)
from sqlalchemy.dialects.mysql import VARBINARY
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.sql import text
# from sqlalchemy.orm.session import Session

# Use for SQlite
# from . import config_db_sqlite as config_db
# from . import config_db
from . import config_db

# PUS_BASE = declarative_base()
# RMAP_BASE = declarative_base()
# FEEDATA_BASE = declarative_base()
DB_BASE = declarative_base()

protocols = {'PUS': ('', DB_BASE),
             'RMAP': ('rmap_', DB_BASE),
             'FEEDATA': ('feedata_', DB_BASE)}


class DbTelemetryPool(DB_BASE):  # type: ignore
    """
    Instances of this class represent rows in the Telemetry Pools' table.
    """
    __tablename__ = protocols['PUS'][0] + config_db.telemetry_pool_table

    # PK, invisible to usercode
    iid = Column(Integer, primary_key=True, nullable=False)

    # When loading a pool from a filedump, pool_name has
    # the filename, and modification_time has the file's mtime.
    # This allows us to avoid reloading the file in the DB
    # unless the data have actually changed (instant-reloads)
    #
    # Live telemetry streams also need a modification_time
    # (the time recording started). The pool_name in that
    # case is whatever the user code sets it to.
    pool_name = Column(Unicode(250, collation='utf8_general_ci'), nullable=False)
    protocol = Column(Unicode(250, collation='utf8_general_ci'), nullable=False)
    modification_time = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('pool_name', name='uniq_pool_name_and_idx'),
    )

    def __init__(self, **kwargs):
        super(DbTelemetryPool, self).__init__(**kwargs)
        # BASE.__init__(self, **kwargs)


class DbTelemetry(DB_BASE):  # type: ignore
    """
    Instances of this class represent rows in the Telemetries table.
    """
    __tablename__ = protocols['PUS'][0] + config_db.telemetry_table
    __table_args__ = (
        UniqueConstraint('pool_id', 'idx', name='uniq_pool_id_and_idx'),
        Index('pool_id_and_idx', 'idx', 'pool_id'),
    )

    # PK, invisible to usercode
    iid = Column(Integer, primary_key=True, nullable=False)

    # FK to pool
    pool_id = Column(Integer,
                     ForeignKey(protocols['PUS'][0] + config_db.telemetry_pool_table + '.iid'))

    # The columns from the treeview control
    idx = Column(Integer, nullable=False, index=True)
    is_tm = Column(Boolean, nullable=False)
    apid = Column(Integer, nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    len_7 = Column(Integer, nullable=False)
    stc = Column(Integer, nullable=False, index=True)
    sst = Column(Integer, nullable=False, index=True)
    destID = Column(Integer, nullable=False)
    timestamp = Column(Unicode(250, collation='utf8_general_ci'), nullable=True,
                       index=True)  # Should this be TIMESTAMP?
    data = Column(VARBINARY(1024), nullable=False)  # Much faster than BLOB
    raw = Column(VARBINARY(1024), nullable=False)  # Much faster than BLOB

    # Helper attribute to access the associated pool.
    pool = relationship("DbTelemetryPool")

    def __init__(self, **kwargs):
        super(DbTelemetry, self).__init__(**kwargs)
        # BASE.__init__(self, **kwargs)


class RMapTelemetry(DB_BASE):  # type: ignore
    """
    Instances of this class represent rows in the RMAP Telemetries table.
    """
    __tablename__ = protocols['RMAP'][0] + config_db.telemetry_table
    __table_args__ = (
        UniqueConstraint('pool_id', 'idx', name='uniq_pool_id_and_idx'),
        Index('pool_id_and_idx', 'idx', 'pool_id'),
    )

    # PK, invisible to usercode
    iid = Column(Integer, primary_key=True, nullable=False)

    # FK to pool
    pool_id = Column(Integer,
                     ForeignKey(config_db.telemetry_pool_table + '.iid'))

    # The columns from the treeview control
    idx = Column(Integer, nullable=False, index=True)
    cmd = Column(Boolean, nullable=False)
    write = Column(Boolean, nullable=False)
    verify = Column(Boolean, nullable=False)
    reply = Column(Boolean, nullable=False)
    increment = Column(Boolean, nullable=False)
    keystat = Column(Integer, nullable=False, index=True)
    taid = Column(Integer, nullable=False, index=True)
    addr = Column(Integer, nullable=True)
    datalen = Column(Integer, nullable=False)
    raw = Column(VARBINARY(2**15), nullable=False)  # Much faster than BLOB

    # Helper attribute to access the associated pool.
    pool = relationship("DbTelemetryPool")

    def __init__(self, **kwargs):
        super(RMapTelemetry, self).__init__(**kwargs)


class FEEDataTelemetry(DB_BASE):  # type: ignore
    """
    Instances of this class represent rows in the RMAP Telemetries table.
    """
    __tablename__ = protocols['FEEDATA'][0] + config_db.telemetry_table
    __table_args__ = (
        UniqueConstraint('pool_id', 'idx', name='uniq_pool_id_and_idx'),
        Index('pool_id_and_idx', 'idx', 'pool_id'),
    )

    # PK, invisible to usercode
    iid = Column(Integer, primary_key=True, nullable=False)

    # FK to pool
    pool_id = Column(Integer,
                     ForeignKey(config_db.telemetry_pool_table + '.iid'))

    # The columns from the treeview control
    idx = Column(Integer, nullable=False, index=True)
    pktlen = Column(Integer, nullable=False)
    type = Column(Integer, nullable=False, index=True)
    framecnt = Column(Integer, nullable=False, index=True)
    seqcnt = Column(Integer, nullable=False, index=True)
    raw = Column(VARBINARY(2**15), nullable=False)  # Much faster than BLOB

    # Helper attribute to access the associated pool.
    pool = relationship("DbTelemetryPool")

    def __init__(self, **kwargs):
        super(FEEDataTelemetry, self).__init__(**kwargs)


'''
class RMapTelemetryPool(RMAP_BASE):  # type: ignore
    """
    Instances of this class represent rows in the Telemetry Pools' table.
    """
    __tablename__ = protocols['RMAP'][0] + config_db.telemetry_pool_table

    # PK, invisible to usercode
    iid = Column(Integer, primary_key=True, nullable=False)

    pool_name = Column(Unicode(250, collation='utf8_general_ci'), nullable=False)
    modification_time = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('pool_name', name='uniq_pool_name_and_idx'),
    )

    def __init__(self, **kwargs):
        super(RMapTelemetryPool, self).__init__(**kwargs)


class FEEDataTelemetryPool(FEEDATA_BASE):  # type: ignore
    """
    Instances of this class represent rows in the Telemetry Pools' table.
    """
    __tablename__ = protocols['FEEDATA'][0] + config_db.telemetry_pool_table

    # PK, invisible to usercode
    iid = Column(Integer, primary_key=True, nullable=False)

    pool_name = Column(Unicode(250, collation='utf8_general_ci'), nullable=False)
    modification_time = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('pool_name', name='uniq_pool_name_and_idx'),
    )

    def __init__(self, **kwargs):
        super(FEEDataTelemetryPool, self).__init__(**kwargs)
'''


#   Creates a session
#   @return: Session
# def connect_to_db(create_tables=False, static_state=[None, None]) -> Session:
#     '''All the work in the database is done inside sessions.
#     (allowing us to commit, rollback, etc)'''
#     # engine, session_factory = static_state
#     # if engine is None:
#     #     engine = create_engine(
#     #         config_db.mysql_connection_string,
#     #         echo="-v" in sys.argv)
#     #     session_factory = sessionmaker(bind=engine)
#     #     static_state[0] = engine
#     #     static_state[1] = session_factory
#     engine = create_engine(config_db.mysql_connection_string, echo="-v" in sys.argv)
#     if create_tables:
#         engine.execute('CREATE SCHEMA IF NOT EXISTS {}'.format(config_db.database_name))
#         engine.dispose()
#         engine = create_engine(config_db.mysql_connection_string + '/' + config_db.database_name, echo="-v" in sys.argv)
#         BASE.metadata.create_all(engine)
#     # return session_factory()


def gen_mysql_conn_str(user=config_db.user, pw=config_db.pw, host=config_db.host, schema=''):
    return engine.url.URL.create(drivername='mysql', username=user, password=pw, host=host, database=schema)


def create_storage_db(protocol='PUS', force=False):
    if protocol.upper() not in ['PUS', 'RMAP', 'FEEDATA', 'ALL']:
        print('Unsupported protocol {}. Use either "PUS", "RMAP", "FEEDATA" or "ALL".'.format(protocol))
        return
    elif protocol.upper() == 'ALL':
        print('Creating schema "{}" for {} data storage...'.format(config_db.storage_schema_name, protocol.upper()))
        _engine = create_engine(gen_mysql_conn_str(), echo="-v" in sys.argv)
        if force:
            _engine.execute(text('DROP SCHEMA IF EXISTS {}'.format(config_db.storage_schema_name)))
        _engine.execute(text('CREATE SCHEMA IF NOT EXISTS {}'.format(config_db.storage_schema_name)))
        _engine.dispose()
        _engine = create_engine(gen_mysql_conn_str(schema=config_db.storage_schema_name), echo="-v" in sys.argv)
        for protocol in protocols:
            protocols[protocol][1].metadata.create_all(_engine)
        print('...DONE')
    else:
        print('Creating schema "{}" for {} data storage...'.format(config_db.storage_schema_name, protocol.upper()))
        _engine = create_engine(gen_mysql_conn_str(), echo="-v" in sys.argv)
        if force:
            _engine.execute(text('DROP SCHEMA IF EXISTS {}'.format(config_db.storage_schema_name)))
        _engine.execute(text('CREATE SCHEMA IF NOT EXISTS {}'.format(config_db.storage_schema_name)))
        _engine.dispose()
        _engine = create_engine(gen_mysql_conn_str(schema=config_db.storage_schema_name), echo="-v" in sys.argv)
        protocols[protocol.upper()][1].metadata.create_all(_engine)
        print('...DONE')


def scoped_session_maker(db_schema, idb_version=None):
    """Create a scoped session maker, returning thread-local sessions
    :param db_schema: either IDB or STORAGE
    :param idb_version: schema name of IDB to be used
    :return:
    """
    if db_schema.lower() == 'idb':
        if idb_version is not None:
            schema = idb_version
        else:
            schema = config_db.idb_schema_name
    elif db_schema.lower() == 'storage':
        schema = config_db.storage_schema_name
    else:
        print('DB schema must be either "idb" or "storage"')
        return
    _engine = create_engine(gen_mysql_conn_str(schema=schema), echo="-v" in sys.argv, pool_size=15)
    session_factory = sessionmaker(bind=_engine)
    scoped_session_factory = scoped_session(session_factory)
    #scoped_session_factory = scoped_session_v2(session_factory)
    return scoped_session_factory


class scoped_session_v2(scoped_session):
    """
    Wrapper class to cast SQL query statement string to TextClause before execution, as this is required since SQLAlchemy 2.0.
    """

    def execute(self, x, *args, **kwargs):
        return super().execute(text(x), *args, **kwargs)


# def load_telemetry_file(dummy: str) -> None:
#     '''Loads a telemetry dumpfile in the database, populating
#     the tm_pool and tm tables.
#     If the data have already been loaded, it does nothing.'''
#     # with open(file_path, 'r') as f:
#     pass  # pragma: no cover


if __name__ == "__main__":
    # if "-pdb" in sys.argv:  # pragma: no cover
    #     sys.argv.remove("-pdb")  # pragma: no cover
    #     from ipdb import set_trace  # NOQA pragma: nocover pylint: disable=C0413,C0411
    #     set_trace()  # pragma: no cover
    # from .test_db import add_example_data  # pragma: no cover
    create_storage_db(force=True, protocol='ALL')  # pragma: no cover
    # add_example_data(sess)  # pragma: no cover

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
