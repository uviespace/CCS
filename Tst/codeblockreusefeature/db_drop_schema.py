import db_schema

if __name__ == '__main__':
    with db_schema.session_scope() as session:
        # drop the database schema
        db_schema.drp_schm()
