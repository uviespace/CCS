from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Index, Integer, String, ForeignKey, Boolean, Text
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from contextlib import contextmanager

mysql_connection_string = 'mysql://egse:weltraummuell@localhost'
schema_name = 'codeblocks'


def crt_ngn():
    a_engine = create_engine(mysql_connection_string + '/' + schema_name, echo=True)
    return a_engine


engine = crt_ngn()


def crt_schm():
    a_engine = create_engine(mysql_connection_string, echo=True)
    a_engine.execute('CREATE DATABASE IF NOT EXISTS {}'.format(schema_name))
    """
    If there comes up a access denied error, try following:
    login into SQL shell as root:
    CREATE DATABASE <schema>;
    GRANT ALL PRIVILEGES ON <schema> . * TO 'smile'@'localhost';
    FLUSH PRIVILEGES;
    """
    return


def drp_schm():
    """
    drop the database scheme
    """
    a_engine = create_engine(mysql_connection_string, echo=True)
    a_engine.execute('DROP DATABASE {}'.format(schema_name))
    return


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Base = declarative_base()


class CodeBlock(Base):
    __tablename__ = 'codeblocks'

    id = Column(Integer, primary_key=True)
    # code_type_id = Column(ForeignKey('codekinds.id'))
    # code_type = relationship('CodeKind')
    code_type = Column(String(20), default='')
    description = Column(Text(10000), default='')
    command_code = Column(Text(10000), default='')
    verification_code = Column(Text(10000), default='')
    # TC
    # is_step
    # is_command_code_block
    # is_verification_code_block
    # requirement IDs
    # verification IDs

    def __repr__(self):
        return '<CodeSnippet(code_type="{}", description="{}", command_code_block="{}", verification_code_block="{}")>'\
            .format(self.code_type, self.description, self.command_code, self.verification_code)

    def data_as_list(self):
        return [self.id, self.code_type, self.description, self.command_code, self.verification_code]


class CodeTestSpec(Base):
    __tablename__ = 'testspecs'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    description = Column(Text(10000))
    version = Column(String(100))
    primary_counter_locked = Column(Boolean(), default=False)
    steps = relationship('CodeStep')


class CodeStep(Base):
    __tablename__ = 'steps'

    id = Column(Integer, primary_key=True)

    code_type = Column(String(20), default='')
    description = Column(Text(10000), default='')
    command_code = Column(Text(10000), default='')
    verification_code = Column(Text(10000), default='')
    test_spec = Column(ForeignKey('testspecs.id'))
    # TC
    # is_step
    # is_command_code_block
    # is_verification_code_block
    # requirement IDs
    # verification IDs

    def __repr__(self):
        return '<CodeSnippet(code_type="{}", description="{}", command_code_block="{}", verification_code_block="{}")>'\
            .format(self.code_type, self.description, self.command_code, self.verification_code)

    def data_as_list(self):
        return [self.id, self.code_type, self.description, self.command_code, self.verification_code]


# class CodeKind(Base):
#     __tablename__ = 'codekinds'
#
#     id = Column(Integer, primary_key=True)
#     code_kind = Column(String(20))
#
#     def __repr__(self):
#         return '<CodeKind("{}")>'.format(self.code_kind)
#
#     def kind(self):
#         return self.code_kind


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if __name__ == '__main__':
    """
    create the schema in the database
    """
    crt_schm()
    Base.metadata.create_all(engine)

    # # add code kinds to the table
    # with session_scope() as session:
    #     session.add_all([
    #         CodeKind(code_kind='snippet'),
    #         CodeKind(code_kind='step')
    #     ])
