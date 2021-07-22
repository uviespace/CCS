import db_schema
#from db_schema import CodeBlock, CodeTestSpec, CodeStep
from db_schema import CodeBlock, Pre_Post_Con
# from db_schema import CodeBlock, CodeKind
# import db_interaction


def dummy_data_code_block():
    session.add_all([
        #CodeBlock(code_type="snippet",
        #          description="Use TC(3,6) to disable the generation of the IFSW_HK housekeeping report",
        #          command_code="# sending a TC(3,6) to disable IFSW_HK housekeeping\ntc_dis = ccs.Tcsend_DB('DPU_IFSW_DIS_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)\ntc_id = tcid.TcId(st=3, sst=6, apid=tc_dis[0], ssc=tc_dis[1], timestamp=tc_dis[2])\n'"),
        #CodeBlock(code_type="snippet",
        #          description="Enable the HK",
        #          command_code="# send TC(3,5)\nccs.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)\n# send TC(3,131)\nccs.Tcsend_DB('DPU_IFSW_SET_HK_REP_FREQ', 1, 8*4, ack='0b1011', pool_name=pool_name)\n"),
        #CodeBlock(code_type="snippet",
        #          description="verify that all three acknowledgements are received",
        #          command_code="tc_dis = tc_id.tc_id_tuple()\n# check if the TC was successful\nresult = tm.check_acknowledgement(ccs=ccs, pool_name=pool_name, tc_identifier=tc_dis)"),
        CodeBlock(code_type="step",
                  description="A step consists out ouf command and verification",
                  comment="This is just a comment for this step",
                  command_code="print('This is the command code')\n",
                  verification_code="print('This is the verification code')",
                  verification_descr="I am describing the verifcation"),
        CodeBlock(code_type="snippet",
                  description="Increase the HK Frequency",
                  comment="Increase the Frequncy to 1 HK per second",
                  command_code="cfl.Tcsend_DB('SASW ModHkPeriodCmd', 1, 8, pool_name='new_tmtc_pool')"),
        Pre_Post_Con(type="pre",
                  name="None",
                  description="No Pre-Condition needed",
                  condition="logger.info('No pre-conditions have been given')\nsuccess = True"),
        Pre_Post_Con(type="post",
                     name="None",
                     description="No Post-Condition needed",
                     condition="logger.info('No post-conditions have been given')\nsuccess = True")

    ])

# No longer used, everything in codeblocks data table
#def dummy_data_steps():
#    session.add_all([
#        CodeStep(
#            code_type="snippet",
#            description="Use TC(3,6) to disable the generation of the IFSW_HK housekeeping report",
#            command_code="# sending a TC(3,6) to disable IFSW_HK housekeeping\ntc_dis = ccs.Tcsend_DB('DPU_IFSW_DIS_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)\ntc_id = tcid.TcId(st=3, sst=6, apid=tc_dis[0], ssc=tc_dis[1], timestamp=tc_dis[2])\n'",
#            test_spec=1),
#        CodeStep(
#            code_type="snippet",
#            description="Enable the HK",
#            command_code="# send TC(3,5)\nccs.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', 1, ack='0b1011', pool_name=pool_name)\n# send TC(3,131)\nccs.Tcsend_DB('DPU_IFSW_SET_HK_REP_FREQ', 1, 8*4, ack='0b1011', pool_name=pool_name)\n",
#            test_spec=1),
#        CodeStep(
#            code_type="snippet",
#            description="verify that all three acknowledgements are received",
#            command_code="tc_dis = tc_id.tc_id_tuple()\n# check if the TC was successful\nresult = tm.check_acknowledgement(ccs=ccs, pool_name=pool_name, tc_identifier=tc_dis)",
#            test_spec=1),
#        CodeStep(
#            code_type="step",
#            description="A step consists out ouf command and verification",
#            command_code="tc_dis = tc_id.tc_id_tuple()\n",
#            verification_code="# check if the TC was successful\nresult = tm.check_acknowledgement(ccs=ccs, pool_name=pool_name, tc_identifier=tc_dis)",
#            test_spec=1)
#    ])

'''
# Basic idea of saving Test Specification is good, but is not needed now
def dummy_data_test_spec():
    session.add_all([
        CodeTestSpec(
            name="DummyTestSpec",
            description="A dummy test specification for database testing purpose",
            version="1.0"
        )
    ])
'''

def query_return_all():
    result = session.query(CodeBlock).all()
    return result


if __name__ == '__main__':
    with db_schema.session_scope() as session:
        dummy_data_code_block()
        #dummy_data_test_spec()
        #dummy_data_steps()
