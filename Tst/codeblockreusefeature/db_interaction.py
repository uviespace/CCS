import db_schema
from db_schema import CodeBlock


def query_get_all_entries():
    with db_schema.session_scope() as session:
        data = session.query(CodeBlock).all()
        session.expunge_all()
    return data


def write_into_db_step(description, command_code, verification_code):
    with db_schema.session_scope() as session:
        new_db_row = CodeBlock(code_type='step', description=description, command_code=command_code, verification_code=verification_code)
        session.add(new_db_row)
    return


def write_into_db_snippet(description, code_block):
    with db_schema.session_scope() as session:
        new_db_row = CodeBlock(code_type='snippet', description=description, command_code=code_block)
        session.add(new_db_row)
    return


def delete_db_row(id):
    with db_schema.session_scope() as session:
        session.query(CodeBlock).filter_by(id=id).delete()
    return


def query_using_textsearch(expressions):
    with db_schema.session_scope() as session:
        data = session.query(CodeBlock).filter(CodeBlock.description.contains(expressions)).all()
        session.expunge_all()
    return data


def query_code_types():
    with db_schema.session_scope() as session:
        data = session.query(CodeBlock.code_type).group_by(CodeBlock.code_type).all()
        session.expunge_all()
    return data


if __name__ == '__main__':
    query_code_types()
