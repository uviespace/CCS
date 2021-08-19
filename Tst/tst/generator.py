import os
import string
import data_model
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()
import db_interaction

cmd_scrpt_auxiliary = '_command.py'
vrc_scrpt_auxiliary = '_verification.py'
run_scrpt_auxiliary = '_run.py'

co_header_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/co_header.py'))
co_class_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/co_class.py'))
co_pre_cond_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/co_pre_condition.py'))
co_step_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/co_step.py'))
co_post_cond_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/co_post_condition.py'))
co_footer_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/co_footer.py'))

run_header_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/run_header.py'))
run_step_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/run_step.py'))
run_footer_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/run_footer.py'))

ver_header_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/ver_header.py'))
ver_class_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/ver_class.py'))
ver_step_path = os.path.normpath(os.path.join(os.path.dirname(__file__), 'generator_templates/ver_step.py'))

def create_file_name(name):
    """
    Take the name of the test specification and make a valid file name out of it
    :param str name: the name which should be transformed into a valid file name
    """
    assert isinstance(name, str)
    file_name = name.replace(' ', '_')
    file_name = file_name.lower()

    return file_name


def create_script_path(name, auxiliary):
    from confignator import config
    dir_pth = config.get_option(section='tst-paths', option='tst_products')
    file_name = create_file_name(name=name)
    script_pth = dir_pth + '/' + file_name + auxiliary
    return script_pth


def create_class_name(name):
    """ Take the name of the test specification and make a valid python class name out of it
    :param str name: the name of the test specification"""
    assert isinstance(name, str)
    class_name = name.replace(' ', '')
    return class_name


def get_product_file_paths(model_name):
    paths = []
    paths.append(create_script_path(name=model_name, auxiliary=cmd_scrpt_auxiliary))
    paths.append(create_script_path(name=model_name, auxiliary=vrc_scrpt_auxiliary))
    paths.append(create_script_path(name=model_name, auxiliary=run_scrpt_auxiliary))
    return paths

def strip_file_extension(name):
    assert type(name) is str
    return name.rsplit('.', 1)[0]


def make_command_script(model, model_spec):
    """ Uses a TST TestSpecification data model and creates a python script out of it.
    A command script has following blocks:

    * header
    * class definition
    * pre condition function
    * step functions
    * post condition function
    * footer

    :param data_model.TestSequence model: A instance of a TST TestSequence data model
    :param model_spec: The above instace of TestSequence, TestSpecification data model
    :return: path were the command script was saved
    :rtype: str
    """
    #assert isinstance(model, data_model.TestSequence)

    content = ''
    indent = '    '

    # add the header (import statements and so on)
    with open(co_header_path, 'r') as header_file_obj:
        header_template_str = header_file_obj.read()
        header_file_obj.close()
        header_str = string.Template(header_template_str)
        header = header_str.substitute(testSpecFileName=create_file_name(model_spec.name))
        # add the header string
        content += header

    # add the class definition
    with open(co_class_path, 'r') as class_file_obj:
        class_template_str = class_file_obj.read()
        class_file_obj.close()

        test_comment_w_indent = model_spec.comment.replace('\n', " ' \\\n".format('\'') + 6 * indent + "'")

        class_str = string.Template(class_template_str)
        cls = class_str.substitute(testSpecClassName=create_class_name(model_spec.name),
                                   testSpecFileName=create_file_name(model_spec.name),
                                   testSpecName=model_spec.name,
                                   testSpecDescription=model_spec.description,
                                   testSpecVersion=model_spec.spec_version,
                                   testIaswVersion=model_spec.iasw_version,
                                   testPreCondition=model_spec.precon_name,
                                   testPostCondition=model_spec.postcon_name,
                                   testComment=test_comment_w_indent)
        # add the header string
        content += '\n\n' + cls

    # add the pre condition function
    with open(co_pre_cond_path, 'r') as pre_cond_file_obj:
        pre_cond_template_str = pre_cond_file_obj.read()
        pre_cond_file_obj.close()

        # Be sure that if it is multiline, that all have the right indent
        pre_con_code = model_spec.precon_code.replace('\n', '\n' + 2 * indent)
        pre_con_descr = model_spec.precon_descr.replace('\n', " ' \\\n" + 6 * indent + "'")

        pre_cond_template = string.Template(pre_cond_template_str)
        pre_cond_combined = pre_cond_template.substitute(TestPreconEntry=pre_con_code,
                                                         TestPreconDescription=pre_con_descr)
        # add the header string
        content += '\n' + pre_cond_combined

    # add the step definitions
    with open(co_step_path, 'r') as step_file_obj:
        step_template_str = step_file_obj.read()
        step_file_obj.close()
        for step in model.steps:
            step_str = string.Template(step_template_str)
            command_code = step.command_code
            command_code_w_indents = command_code.replace('\n', '\n' + 3 * indent)
            step_comment_w_indents = step.step_comment.replace('\n', " ' \\\n" + 5 * indent + "'")
            step_descr_w_indents = step.description.replace('\n', " ' \\\n" + 5 * indent + "'")
            if len(command_code_w_indents) == 0:
                command_code_w_indents = 'pass'
            step = step_str.substitute(testStepNumber=step.step_number_test_format,
                                       testStepDescription=step_descr_w_indents,
                                       testStepComment=step_comment_w_indents,
                                       testStepCommandCode=command_code_w_indents,
                                       testSpecFileName=create_file_name(model_spec.name),
                                       testSpecClassName=create_class_name(model_spec.name))
            # add the string for a steps
            content += '\n' + step

    # add the post condition function
    with open(co_post_cond_path, 'r') as post_cond_file_obj:
        post_cond_template_str = post_cond_file_obj.read()
        post_cond_file_obj.close()

        # Be sure that if it is multiline, that all have the right indent
        post_con_code = model_spec.postcon_code.replace('\n', '\n' + 2 * indent)
        post_con_descr = model_spec.postcon_descr.replace('\n', " ' \\\n" + 6 * indent + "'")

        post_cond_template = string.Template(post_cond_template_str)
        post_cond_combined = post_cond_template.substitute(TestPostconEntry=post_con_code,
                                                           TestPostconDescr=post_con_descr)

        #post_cond_combined.replace('\n', '\n' + 3 * indent)

        # add the header string
        content += '\n' + post_cond_combined

    # add the footer run and other functions)
    with open(co_footer_path, 'r') as footer_file_obj:
        footer_template_str = footer_file_obj.read()
        footer_file_obj.close()
        # build the array of function calls for the steps
        step_arr = ''
        for step in model.steps:
            #step_arr += '\n' + 4 * indent + 'self.step_' + str(model.steps[step].step_number) + ','
            step_arr += '\n' + 4 * indent + 'self.step_' + str(step.step_number_test_format) + ','
        footer_str = string.Template(footer_template_str)
        foot = footer_str.substitute(testStepsList=step_arr)
        content += '\n' + foot

    # create the new file
    file_path = create_script_path(name=model_spec.name, auxiliary=cmd_scrpt_auxiliary)
    with open(file_path, 'w') as command_script:
        command_script.write(content)
        command_script.close()
    print('Command script was saved under {}'.format(file_path))

    return file_path


def make_command_run_script(model, model_spec):
    #assert isinstance(model, data_model.TestSequence)

    content = ''
    indent = '    '

    # add the header (import statements and so on)
    with open(run_header_path, 'r') as header_file_obj:
        header_template = header_file_obj.read()
        header_file_obj.close()

        precon_descr_w_indent = model_spec.precon_descr.replace('\n', '\n{}#{}'.format(indent, 4*indent))

        # add the header string
        header_template_str = string.Template(header_template)
        #header_str = header_template_str.substitute(testSpecClassName=create_class_name(model.name),
        #                                            testSpecFileName=create_file_name(model.name),
        #                                            testPrecondDesc=model.pre_condition.description)
        header_str = header_template_str.substitute(testSpecClassName=create_class_name(model_spec.name),
                                                    testSpecFileName=create_file_name(model_spec.name),
                                                    TestPreconDescription=precon_descr_w_indent)

        content += header_str

    # add the step definitions
    with open(run_step_path, 'r') as step_file_obj:
        step_template_str = step_file_obj.read()
        step_file_obj.close()
        for step in model.steps:
            step_descr_w_indent = step.description.replace('\n', '\n{}#{}'.format(indent, 3*indent))
            step_str = string.Template(step_template_str)
            #step = step_str.substitute(testStepNumber=model.steps[step].step_number,
            #                           testStepDescription=model.steps[step].description,
            #                           testStepComment=model.steps[step].comment)
            step = step_str.substitute(testStepNumber=step.step_number_test_format,
                                       testStepDescription=step_descr_w_indent)
            # add the string for a steps
            content += '\n' + step

    # add the step definitions
    with open(run_footer_path, 'r') as footer_file_obj:
        footer_template_str = footer_file_obj.read()
        footer_file_obj.close()

        postcon_descr_w_indent = model_spec.postcon_descr.replace('\n', '\n{}#{}'.format(indent, 4*indent))

        footer_template_str = string.Template(footer_template_str)
        footer = footer_template_str.substitute(TestPostconDescription=postcon_descr_w_indent)

        content += '\n' + footer

    # create the new file
    file_path = create_script_path(name=model_spec.name, auxiliary=run_scrpt_auxiliary)
    with open(file_path, 'w') as command_script:
        command_script.write(content)
        command_script.close()
    print('Command script was saved under {}'.format(file_path))

    return file_path


def make_verification_script(model, model_spec):
    #assert isinstance(model, data_model.TestSequence)

    content = ''
    indent = '    '

    # add the header (import statements and so on)
    with open(ver_header_path, 'r') as header_file_obj:
        header_template_str = header_file_obj.read()
        header_file_obj.close()

        # add the header string
        content += header_template_str

    # add the class definition
    with open(ver_class_path, 'r') as class_file_obj:
        class_template_str = class_file_obj.read()
        class_file_obj.close()
        class_str = string.Template(class_template_str)
        cls = class_str.substitute(testSpecClassName=create_class_name(model_spec.name),
                                   testSpecFileName=create_file_name(model_spec.name),
                                   testSpecName=model_spec.name,
                                   testSpecDescription=model_spec.description,
                                   testSpecVersion=model_spec.spec_version)
        # add the header string
        content += '\n\n' + cls

    # # add the pre condition function
    # with open(pre_cond_path, 'r') as pre_cond_file_obj:
    #     pre_cond_template_str = pre_cond_file_obj.read()
    #     pre_cond_file_obj.close()
    #     # add the header string
    #     content += '\n' + pre_cond_template_str

    # add the step definitions
    with open(ver_step_path, 'r') as step_file_obj:
        step_template_str = step_file_obj.read()
        step_file_obj.close()
        for step in model.steps:
            step_str = string.Template(step_template_str)
            verification_code = step.verification_code
            verification_code_w_indents = verification_code.replace('\n', '\n' + 3 * indent)
            verification_descr_w_indents = step.step_comment.replace('\n', " ' \\\n" + 6 * indent + "'")
            step_descr_w_indents = step.description.replace('\n', " ' \\\n" + 5 * indent + "'")
            if len(verification_code_w_indents) == 0:
                verification_code_w_indents = 'pass'
            #step = step_str.substitute(testStepNumber=model.steps[step].step_number,
            #                           testStepDescription=model.steps[step].description,
            #                           testStepComment=model.steps[step].comment,
            #                           testStepVerificationCode=verification_code_w_indents)
            step = step_str.substitute(testStepNumber=step.step_number_test_format,
                                       testStepDescription=step_descr_w_indents,
                                       testStepVerificationDescription=verification_descr_w_indents,
                                       testStepVerificationCode=verification_code_w_indents)
            # add the string for a steps
            content += '\n' + step

    # add the footer (logger_setup)
    #with open(ver_footer_path, 'r') as footer_file_obj:
    #    footer_template_str = footer_file_obj.read()
    #    footer_file_obj.close()

        # add the header string
    #    content += footer_template_str

    # # add the post condition function
    # with open(post_cond_path, 'r') as post_cond_file_obj:
    #     post_cond_template_str = post_cond_file_obj.read()
    #     post_cond_file_obj.close()
    #     # add the header string
    #     content += '\n' + post_cond_template_str
    #
    # # add the footer (post condition and other functions)
    # with open(footer_path, 'r') as footer_file_obj:
    #     footer_template_str = footer_file_obj.read()
    #     footer_file_obj.close()
    #     # build the array of function calls for the steps
    #     step_arr = ''
    #     for step in model.steps_dict:
    #         step_arr += '\n' + 4 * indent + 'self.step_' + str(model.steps_dict[step].step_number) + ','
    #     footer_str = string.Template(footer_template_str)
    #     foot = footer_str.substitute(testStepsList=step_arr)
    #     content += '\n' + foot

    # create the new file
    file_path = create_script_path(name=model_spec.name, auxiliary=vrc_scrpt_auxiliary)
    with open(file_path, 'w') as command_script:
        command_script.write(content)
        command_script.close()
    print('Verification script was saved under {}'.format(file_path))

    return file_path


def make_documentation(model, model_spec):
    return None


def make_all(model):
    paths = []
    # TODO: Only one Sequence is supported here
    for sequence in model.sequences:
        cs_path = make_command_script(sequence, model)
        cms_path = make_command_run_script(sequence, model)
        vf_path = make_verification_script(sequence, model)
        dc_path = make_documentation(sequence, model)
        break

    #cs_path = make_command_script(model)
    #cms_path = make_command_manually_steps_script(model)
    #vf_path = make_verification_script(model)
    #dc_path = make_documentation(model)

    if cs_path is not None:
        paths.append(cs_path)
    if cms_path is not None:
        paths.append(cms_path)
    if vf_path is not None:
        paths.append(vf_path)
    if dc_path is not None:
        paths.append(dc_path)

    return paths
