import os
import sys

START = """import sys
import os
sys.path.append(confignator.get_option('paths', 'ccs'))
from Ccs import ccs_function_lib as cfl

cfl.enable_save_parameters()

file = open("params_log.txt", "w")
file.close()
"""

write_step = """file = open("params_log.txt", "a")
file.write("{}" + "\\n")
file.close()"""

write_r_step = """file = open("params_log.txt", "a")
file.write(r"{}" + "\\n")
file.close()"""

FINAL = """
os.rename("params_log.txt", "{}")
"""

# Check if the input path is provided as a command-line argument
if len(sys.argv) < 2:
    print("Usage: python script_for_readout.py <input_path>")
    sys.exit(1)

input_path = sys.argv[1]
output_path = os.path.join(input_path + "_readout")

# Create the output directory if it doesn't exist
os.makedirs(output_path, exist_ok=True)

# Filter Python files in the input directory, excluding specific patterns
file_list = [
    input_path + os.sep + file
    for file in os.listdir(input_path)
    if "for_readout" not in file and "merge" not in file and file.endswith(".py")
]

print("Converting Python files to readout format...")
for file in file_list:
    # Generate the new file name with "_for_readout" suffix
    new_file = file.replace(".py", "_for_readout.py")
    new_text = [START]  # Start with the predefined header

    with open(file, "r") as r:
        f = r.readlines()

        for line in f:
            # Convert comments to log-writing steps unless they contain "STEP"
            if line.startswith("# ") and not "STEP" in line:
                line = write_step.format(line[:-1]) + "\n"
            # Handle lines containing "STEP" with a newline prefix
            elif "STEP" in line:
                line = write_step.format("\\n" + line[:-1]) + "\n"

            new_text.append(line)

    # Append the final renaming step and clean up redundant file operations
    text = "".join(new_text) + FINAL.format(file.replace(".py", "") + "_commands.txt")
    text = text.replace("""file.close()\nfile = open("params_log.txt", "a")\n""", "")
    text = text.replace("""file.close()\n\n#! CCS.BREAKPOINT\n\nfile = open("params_log.txt", "a")\n""", "\n#! CCS.BREAKPOINT\n\n")
    # text = text.replace("""file.write(    "# Tmpack""", """file.write(r"# Tmpack""    ")

    # Write the processed content to the new file
    with open(new_file, "w") as w:
        w.write(text)

print("Your converted python files are in the directory: " + output_path)
print("done")