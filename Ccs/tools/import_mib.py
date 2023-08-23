#!/usr/bin/env python3

# Generate SQL statements from SCOS2000 cfg file
# Create MySQL schema
# Insert data from MIB files

import json
import os
import sys
import getpass

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text


sdir = os.path.dirname(os.path.abspath(__file__))

FNAME = os.path.join(sdir, 'scos2000db.json')
WBSQL = os.path.join(sdir, 'mk_scos2000_schema.wbsql')

ssd = json.load(open(FNAME, 'r'))


def generate_wbsql():
    with open(WBSQL, 'w') as fdesc:
        fdesc.write('\n'.join(ssd['prologue']) + '\n\n')

        # generate SQL statements for schema creation
        schema = ssd['schema']
        schema['name'] = DBNAME
        txt = 'CREATE SCHEMA IF NOT EXISTS `{}` DEFAULT CHARACTER SET {} COLLATE {} ;\nUSE `{}`;'.format(
            schema['name'], schema['default_character_set'], schema['collate'], schema['name'])
        fdesc.write(txt + '\n\n')

        # add tables
        for tab in ssd['tables']:
            txt = '-- Table {}.{}\nCREATE  TABLE IF NOT EXISTS `{}`.`{}` ('.format(schema['name'], tab, schema['name'], tab)
            fdesc.write(txt + '\n')

            # columns
            txt = '\n'.join(['  `{}`{},'.format(i, ssd['tables'][tab]['columns'][i]) for i in ssd['tables'][tab]['columns']])
            fdesc.write(txt + '\n')

            # options
            txt = '\n'.join(ssd['tables'][tab]['options'])
            txt = txt.replace('$SCHEMA', schema['name'])
            fdesc.write(txt + ' )\n')

            txt = 'ENGINE = {}\nDEFAULT CHARACTER SET = {};'.format(ssd['tables'][tab]['engine'],
                                                                    ssd['tables'][tab]['default_character_set'])
            fdesc.write(txt + '\n\n')

        fdesc.write('\n'.join(ssd['epilogue']))

    print('SQL statements exported to {}'.format(WBSQL))


def create_schema():
    eng = create_engine(DBURL)
    sf = sessionmaker(bind=eng)
    s = sf()

    # delete database schema
    print('...drop schema {}'.format(DBNAME))
    s.execute(text('DROP SCHEMA IF EXISTS {}'.format(DBNAME)))

    # create database schema
    print('...create schema {}'.format(DBNAME))
    s.execute(text(open(WBSQL).read()))
    s.close()


def import_mib():
    eng = create_engine(DBURL + '/' + DBNAME)
    sf = sessionmaker(bind=eng)
    s = sf()

    fs = [k + '.dat' for k in ssd['tables']]

    print('...populating schema {} with data from {}'.format(DBNAME, MIBDIR))

    for fn in fs:
        mfile = open(os.path.join(MIBDIR, fn)).readlines()

        # replace empty strings with DEFAULT
        rows = [('"' + i.replace('\t', '","').strip() + '"').replace('""', 'DEFAULT') for i in mfile]
        try:
            for row in rows:
                s.execute(text('INSERT IGNORE INTO {} VALUES ({})'.format(fn[:-4], row)))  # IGNORE truncates too long strings
        except Exception as err:
            s.rollback()
            s.close()
            raise err

    s.commit()
    s.close()


if __name__ == '__main__':

    do_import = True

    if '-c' in sys.argv:
        MIBDIR = '/home/user/space/mib'  # directory containing the SCOS2000 *.dat files
        DBNAME = 'mib_schema_test'  # SQL schema name to be created
        DBURL = 'mysql://user:password@127.0.0.1'  # credentials of MySQL account

    elif '--dummy' in sys.argv:
        sys.argv.remove('--dummy')
        DBNAME, dbuser = sys.argv[-2:]
        dbpw = getpass.getpass()
        DBURL = 'mysql://{}:{}@127.0.0.1'.format(dbuser, dbpw)
        do_import = False

    elif len(sys.argv) > 3:
        MIBDIR, DBNAME, dbuser = sys.argv[1:4]
        dbpw = getpass.getpass()
        DBURL = 'mysql://{}:{}@127.0.0.1'.format(dbuser, dbpw)

    else:
        print('USAGE: ./import_mib.py <MIBDIR> <DBSCHEMA> <DBUSERNAME> [-c]\n'
              'Options:\n\t-c\tUse configuration in script, any command line arguments will be ignored.\n'
              '\t--dummy\tCreate empty MIB structure only. Omit <MIBDIR> argument.')

        sys.exit()

    generate_wbsql()
    create_schema()

    if do_import:
        import_mib()

    print('...DONE!')
