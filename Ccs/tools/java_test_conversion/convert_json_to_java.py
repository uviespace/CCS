#!/usr/bin/env python3
"""

author: Christopher Granabetter
date: 05.05.2025
edited: 
"""

import datetime
import os
import re
import json
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()
from time import time


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
            // byte[] data = spwPkt.getData();

            byte[] pkt = new byte[1032];
        """
END = """
        }
    }
}
"""

def send_bytes(byte_array):

    print("Sending bytes:", byte_array, type(byte_array))

    # dummy pkt byte string SpW packets not included
    pkt_byte_str = "".join([f"pkt[{i+4}] = (byte) {hex(byte)};\n            " for i, byte in enumerate(byte_array)])

    return f"""

            // to send: {byte_array}
            // list: {[hex(i) for i in list(byte_array)]}
            // sequence counter: {sequence_counter(byte_array)}

            Arrays.fill(pkt, (byte) 0);

            // Spacewire Destination Address
            pkt[0] = 82;
            pkt[1] = 0x02;
			pkt[2] = 0x00;
			pkt[3] = 0x00;

            // Cargo
            {pkt_byte_str}

            getSpwN().transmit(pkt,  simtg.simops.plugin.spacewire.SpwSeqPlugin.EOP);

            sim.timeStep(1);
			
			//System.out.println(Arrays.toString(data));
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


def sequence_counter(data):
    lower6 = data[2] & 0x3F
    next_byte = data[3]
    return (lower6 << 8) | next_byte

def run(jfile, output_path):

    if os.path.isfile(jfile):
        data = json.load(open(jfile, 'r'))
    else:
        data = json.loads(jfile)

    date = datetime.datetime.now().strftime('%Y-%m-%d')

    java_file = os.path.basename(jfile).replace(".json","").replace("-", "_").replace(".", "") + ".java"
    script = make_start(java_file[:-5])

    script += log_note('--------------------------------------------')
    script += log_note(data['_name'])
    script += log_note(data['_description'])
    script += log_note('Specification Version: ' + data['_spec_version'])
    script += log_note('Software Version: ' + data['_iasw_version'])
    script += log_note('Author: UVIE')
    script += log_note('Date: {}'.format(date))
    script += log_note('--------------------------------------------')
    script += log_note('COMMENT: {}'.format(data['_comment'].replace('\n', '\n# ')))

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

    namespace = {"cfl": cfl,
                 "tcs": [],
                 "time": time,}
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
        txt += log_note('{}'.format(step['_description']).replace('\n', ''))

        # TODO: Add the command code, extract byte_str
        # if _tcsend_common in code pick tc
        # if Tcsend_DB --> Tcbuild pick return

        print("\n\n")
        cmd_code = cmd_code.replace("cfl.Tcsend_DB", "tc, tc_para = cfl.Tcbuild").replace("sent = cfl._tcsend_common", "# sent = cfl._tcsend_common")
        cmd_code_lines = cmd_code.splitlines()
        skip_i = None
        for i_code_lines, line in enumerate(cmd_code_lines):
            if i_code_lines == skip_i:
                skip_i = None
                continue

            indent = re.match(r"\s*", line).group()
            if "Tcbuild" in line:
                if not "wrong Source ID" in step['_description']:
                    cmd_code_lines.insert(i_code_lines+1, indent + "try: cfl.counters[int(str(apid), 0)] += 1\n" + indent + "except: cfl.counters[int(str(tc_para[-1]), 0)] += 1")
                    skip_i = i_code_lines + 1
                    
        cmd_code = "\n".join(cmd_code_lines) + "\n"

        if ("\nfor" in cmd_code or cmd_code.startswith("for")) and "    tc" in cmd_code or "\ttc" in cmd_code:
            cmd_code = "tcs = []\n" + cmd_code
            cmd_code += "    tcs.append(tc)"
            print(data['_name'])
            print(step['_step_number'])
            print(cmd_code)
            exec(cmd_code, namespace)
            result = namespace["tcs"] if "tcs" in namespace else None
        else:
            print(data['_name'])
            print(step['_step_number'])
            print(cmd_code)
            exec(cmd_code, namespace)
            result = namespace["tc"] if "tc" in namespace else None
        
        print("Returned:", result)
        if isinstance(result, bytes):
            txt += send_bytes(result)
        elif isinstance(result, list):
            for tc in result:
                if isinstance(tc, bytes):
                    txt += send_bytes(tc)
                elif isinstance(tc, tuple):
                    print("here")
                    txt += send_bytes(tc[0])
                else:
                    txt += '\n            // No bytes to send'
                #txt += send_bytes(tc)
        else:
            txt += '\n            // No bytes to send'

        txt += log_note('VERIFICATION: {}'.format(step['_verification_description'])) if step['_verification_description'] != '' else ''
        if comment != '':
            txt += log_note('COMMENT: {}'.format(comment))

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

    script += log_note('POSTCONDITIONS: {}'.format(data['_postcon_descr']))
    # script += data['_postcon_code'].strip()  # Add the postcondition code

    # if reportfunc:
    #     script += '\nreport.export()\n\n'

    script += END

    with open(os.path.join(output_path, java_file), 'w') as fd:
        fd.write(script)



if __name__ == '__main__':

    not_functional_files = ["/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-5_1-TS-0.2.json",   # ValueError: Range check failed - Invalid parameter value for event_id: EVT_CMD_INV_APID
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-20_1-TS-0.2.json",  # KeyError: "1"
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-9_1-TS-0.2.json",   # struct.error: bad char in struct format
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-213_1-TS-0.2.json", # not readys
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-212_1-TS-0.2.json", # struct.error: 'H' format requires 0 <= number <= 65535
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-194_1-TS-0.2.json", # ValueError: Range check failed - Invalid parameter value for AlgoId: 1 [valid: TC_ALGO]
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-3_1-TS-0.2.json",   # STEP 28 not possible to generate in CCS
                            "/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-198_1-TS-0.2.json", # ValueError: Range check failed - Invalid parameter value for ProcId: WRONG [valid: CAL_FULL | CHECKOUT_PR | DWN_TRANS_PR | OPER_PR]
                            ] 

    json_file_path = r"/home/christopher/FSW/Documents/testspec/tst/FFT_draft_spec02/IASW-SRV-1_1-TS-0.2.json"
    # Check if the input path is provided as a command-line argument
    if len(sys.argv) < 2:
        print("Usage: python convert_json_to_java.py <input_path>")
        sys.exit(1)

    input_path = sys.argv[1]
    if os.path.isfile(input_path):
        json_files = [input_path]
    else:
        json_files = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.endswith('.json')]

    output_path = os.path.join(os.path.dirname(input_path) + "_java")

    os.makedirs(output_path, exist_ok=True)

    for json_file in json_files:

        if json_file in not_functional_files:
            continue

        print("Converting JSON file to Java...")
        print(json_file)
        run(json_file, output_path)
        print("Your converted JSON files are in the directory: " + output_path)

