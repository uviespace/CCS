#!/usr/bin/env python3
"""

author: Christopher Granabetter
date: 05.05.2025
edited: 
"""

import datetime
import os
import json
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()

MIB_VERSION = '1.8.1'

def make_start(filename):
    return f"""package pl_cbk_fgs_ariel.ut;

import simtg.simops.base.SimopsException;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import pl_cbk_fgs_ariel.common.PlCbkFgsArielTestSequence;
import pl_cbk_fgs_ariel.common.TcPusPkt;
import pl_cbk_fgs_ariel.common.TmPusPkt;
import simtg.simops.plugin.spacewire.SpwPlugin;
import simtg.simops.plugin.spacewire.SpwSeqPlugin;
import simtg.simops.plugin.spacewire.SpwSpyDynamic;
import simtg.simops.plugin.spacewire.SpwSpyPacket;
import simtg.simops.plugin.spacewire.SpwSeqPlugin;

public class {filename} extends PlCbkFgsArielTestSequence {{

    public static void main(String[] args) {{
        new {filename}().run();
    }}

    @Override
    public void sequence() throws SimopsException {{
        tester.logSection("Start of test");
        {{
            createDpuBench();
			getSpwN().bind("stubSpwN");
			getSpwR().bind("stubSpwR");
			SpwSpyDynamic spySpwN = getSpwN().getSpyManager().addSpyBuffer("mySpy");
			SpwSpyDynamic spySpwR = getSpwR().getSpyManager().addSpyBuffer("mySpy");

			getSpwN().connect(dpuName + ".SPWN");
			getSpwR().connect(dpuName + ".SPWR");

            tester.logStep("Init model");
            sim.init();

            tester.logStep("Testing Boot");
			sim.writeBoolean(dpuName + ".In.pwrN", true);
			sim.activateMethod(dpuName + ".BootSwHandover");
			
			
			sim.timeStep(15.0);
			
			sim.timeStep(15.0);
			
			sim.timeStep(3.0);
			

			getSpwN().isLinkStarted();

            SpwSpyPacket spwPkt = spySpwN.getPacket();
            byte[] data = spwPkt.getData();

            byte[] pkt = new byte[1032];
        """
END = """
        }
    }
}
"""

def send_bytes(byte_array):

    # dummy pkt byte string SpW packets not included
    pkt_byte_str = "".join([f"pkt[{i+4}] = (byte) {byte};\n            " for i, byte in enumerate(byte_array)])
    
    return f"""

            Arrays.fill(pkt, (byte) 0);

            pkt[0] = 82;
            pkt[1] = 0x02;
			pkt[2] = 0x00;
			pkt[3] = 0x00;
            {pkt_byte_str}

            getSpwN().transmit(pkt,  simtg.simops.plugin.spacewire.SpwSeqPlugin.EOP);

            sim.timeStep(1);
			
			System.out.println(Arrays.toString(data));
			tester.logSection("Check msg");
			sim.activateMethod(dpuName + ".dumpTm");
        """

def log_section(desc):
    return f"""
            tester.logSection("{desc}");"""

def log_step(desc):
    return f"""
            tester.logStep("{desc}");"""

def log_note(desc):
    return f"""
            sim.insertLog("{desc}");"""

def parse_command_file(file_path):
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return None
    except IOError as e:
        print(f"Error reading file {file_path}: {e}")
        return None


def run(jfile, outfile, reportfunc=False, specfile=None):

    if os.path.isfile(jfile):
        data = json.load(open(jfile, 'r'))
    else:
        data = json.loads(jfile)

    date = datetime.datetime.now().strftime('%Y-%m-%d')

    script = make_start(os.path.basename(jfile).replace(".json","").replace("-", "_").replace(".", ""))

    script += log_note('#--------------------------------------------')
    script += log_note('# ' + data['_name'])
    script += log_note('# ' + data['_description'])
    script += log_note('# Specification Version: ' + data['_spec_version'])
    script += log_note('# Software Version: ' + data['_iasw_version'])
    script += log_note('# Author: UVIE')
    script += log_note('# Date: {}'.format(date))
    script += log_note('#--------------------------------------------')
    script += log_note('# COMMENT: {}'.format(data['_comment'].replace('\n', '\n# ')))

    # if reportfunc:
    #     if specfile is None:
    #         specfile = '{}-TS-{}.csv_PIPE'.format(data['_name'], data['_spec_version'])
    #     script += 'specfile = "{}"\n'.format(specfile)
    #     script += 'rep_version = 1\n'
    #     script += 'mib_version = "{}"\n'.format(MIB_VERSION)
    #     script += 'ask_tc_exec = True\n'
    #     script += 'report = cfl.TestReport(specfile, rep_version, mib_version, gui=True)\n\n'

    # # init code
    # script += '# INIT CODE\n{}\n#! CCS.BREAKPOINT\n\n'.format(data.get('_custom_imports'))

    script += log_note('PRECONDITIONS: {}'.format(data['_precon_descr']))
    # script += '{}\n\n\n'.format(data['_precon_code'].strip())  # Add the precondition code

    for step in data['sequences'][0]['steps']:
        comment = log_note('COMMENT: {}'.format(step['_step_comment'])) if step['_step_comment'] != '' else ''
        cmd_code = step['_command_code'].strip()
        cmd_code += '\n' if cmd_code else ''

        # if reportfunc:
        #     step_tag = 'Step {}'.format(step['_step_number'])
        #     exec_step = 'report.execute_step("{}", ask=ask_tc_exec)\n'.format(step_tag)
        #     verif_step = 'report.verify_step("{}")\n'.format(step_tag)
        # else:
        #     exec_step = ''
        #     verif_step = ''

        txt = "\n" + log_step('STEP {}'.format(step['_step_number']))
        txt += log_note('{}'.format(step['_description']))

        # TODO: Add the command code, extract byte_str
        # if _tcsend_common in code pick tc
        # if Tcsend_DB --> Tcbuild pick return

        cmd_code = cmd_code.replace("cfl.Tcsend_DB", "tc = cfl.Tcbuild")
        print(cmd_code)
        namespace = {"cfl": cfl}  # Provide only what's needed externally
        exec(cmd_code, namespace)

        # Now extract the result
        result = namespace["tc"] if "tc" in namespace else None
        print("Returned:", result)
        #txt += send_bytes(step['_command_code'].strip()) if step['_command_code'] != '' else ''

        txt += log_note('VERIFICATION: {}'.format(step['_verification_description'])) if step['_verification_description'] != '' else ''
        if comment != '':
            txt += log_note('# {}'.format(comment))

        # txt = '# STEP {}\n' \
        #       '# {}\n' \
        #       '{}' \
        #       '{}' \
        #       '# VERIFICATION: {}\n{}{}\n#! CCS.BREAKPOINT\n\n'.format(step['_step_number'], replace_newline(step['_description']), exec_step,
        #                                                               cmd_code,
        #                                                               replace_newline(step['_verification_description']),
        #                                                               verif_step,
        #                                                               # step['_verification_code'].strip(), # Add verification code
        #                                                               comment)

        script += txt

    script += log_note('POSTCONDITIONS\n# {}\n'.format(data['_postcon_descr']))
    # script += data['_postcon_code'].strip()  # Add the postcondition code

    # if reportfunc:
    #     script += '\nreport.export()\n\n'

    if outfile[-1] == '/':  # If path is given not the actual filename
        outfile = outfile + data['_name'] + '-TS-' + '-'.join(data['_spec_version']) + '.java'

    with open(outfile, 'w') as fd:
        fd.write(script)



if __name__ == '__main__':

    json_file_path = r"/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-3_1-TS-0.2.json"
    #json_file_path = sys.argv[1]

    if len(sys.argv) > 2:  # If filename is given
        outputfile = sys.argv[2]
    else:  # If no filename is given take the working directory path, filename is used from the json file
        outputfile = os.getcwd() + '/'
        #outputfile = '/'.join(json_file_path[:-len(json_file_path.split('/')[-1])-1]) + '/'  # This would take the json File path

    run(json_file_path, outputfile, reportfunc=False)
