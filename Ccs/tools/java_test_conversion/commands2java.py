import os
import ast

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

# def prod_step(size, addr, apid, seq, pktLen, st, sst, sdid, data, ce=1, pe=0, se=1, a=1):
#     return f"""
#         /*{{
#             int sizeTc = {size};
#             int addr = (int) {addr};
#             short apid = (short) {apid};
#             short seqCnt = (short) {seq};
#             short pktLen = (short) {pktLen};
#             byte ce = (byte) {ce};
#             byte pe = (byte) {pe};
#             byte se = (byte) {se};
#             byte a = (byte) {a};
#             byte serTypeId = (byte) {st};
#             byte msgTypeId = (byte) {sst};
#             byte srcId = (byte) {sdid};
#             byte [] data = {data};
#             char [] msgTc = new char[sizeTc];

#             TcPusPkt tc = new TcPusPkt(addr, apid, seqCnt, pktLen, ce, pe, se, a, serTypeId, msgTypeId, srcId, data);
#             tc.buildPkt(msgTc);
#             sim.writeCharArray(spwNodeN + ".In.mstTx", msgTc);
#             sim.activateMethod(spwNodeN + ".triggerTransmission", ""+sizeTc);
#         }}*/
#         """

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

    full_text = make_start(os.path.basename(file_path).split("_commands")[0].replace("-", "_").replace(".", ""))
    params_detected = False

    for line in lines:
        line = line.strip()

        if "STEP" in line:
            step_desc = line.split("STEP ")[1]
            full_text += f"\n\n\t\t\t// {line}"
            full_text += log_step(step_desc)
            params_detected = False

        elif line.startswith("{"):
            try:
                # params = ast.literal_eval(line.split(", 'header'")[0] + "}")
                params_detected = True
            except (SyntaxError, ValueError) as e:
                print(f"Error parsing parameters in line: {line}\n{e}")
                continue

        elif line.startswith("b'"):
            if params_detected:
                try:
                    byte_array = [hex(num) for num in list(ast.literal_eval(line))]
                    full_text += send_bytes(byte_array)
                except (SyntaxError, ValueError) as e:
                    print(f"Error parsing byte array in line: {line}\n{e}")
                    continue

        elif "IASW-SRV" in line:
            full_text += log_section(line.replace("# ", ""))

        elif line.startswith("#"):
            full_text += log_note(line.replace("# ", ""))

    full_text += END
    return full_text


cmds_dir = "commands"
try:
    cmds_list = [os.path.join(cmds_dir, file) for file in os.listdir(cmds_dir) if file.endswith("_commands.txt")]
except FileNotFoundError:
    print(f"Error: Directory {cmds_dir} not found.")
except IOError as e:
    print(f"Error accessing directory {cmds_dir}: {e}")

for file_path in cmds_list:
    new_filename = file_path.replace(".", "").replace("_commandstxt", ".java").replace("-", "_")
    java_code = parse_command_file(file_path)
    if java_code:
        try:
            with open(new_filename, "w") as ofile:
                ofile.write(java_code)
            print(f"Generated: {new_filename}")
        except IOError as e:
            print(f"Error writing to file {new_filename}: {e}")

