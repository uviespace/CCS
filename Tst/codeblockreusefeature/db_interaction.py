import db_schema
from db_schema import CodeBlock, Pre_Post_Con


def query_get_all_entries():
    with db_schema.session_scope() as session:
        data = session.query(CodeBlock).all()
        session.expunge_all()
    return data


def write_into_db_step(description, comment, command_code, verification_code, verification_descr):
    with db_schema.session_scope() as session:
        new_db_row = CodeBlock(code_type='step', description=description, comment=comment, command_code=command_code, verification_code=verification_code, verification_descr=verification_descr)
        session.add(new_db_row)
    return


def write_into_db_snippet(description, comment, code_block):
    with db_schema.session_scope() as session:
        new_db_row = CodeBlock(code_type='snippet', description=description, comment=comment, command_code=code_block)
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


# -------------- Pre-Post Condition -------------------
def write_into_pre_post_con(code_type, name, description, code_block):
    # Check if the name already exists
    data = get_pre_post_con(code_type)
    for condition in data:
        if name == condition.name:  # If name exists delete it
            delete_db_row_pre_post(condition.id)
    with db_schema.session_scope() as session:
        new_db_row = Pre_Post_Con(type=code_type, name=name, description=description, condition=code_block)
        session.add(new_db_row)
    return


def delete_db_row_pre_post(id):
    with db_schema.session_scope() as session:
        session.query(Pre_Post_Con).filter_by(id=id).delete()
    return


def get_pre_post_con(code_type):
    with db_schema.session_scope() as session:
        if code_type is None:
            data = session.query(Pre_Post_Con).all()
        else:
            data = session.query(Pre_Post_Con).filter(Pre_Post_Con.type.contains(code_type)).all()
        session.expunge_all()
    return data


if __name__ == '__main__':
    query_code_types()
