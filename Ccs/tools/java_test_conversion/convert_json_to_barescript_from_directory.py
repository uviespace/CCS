import os
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()
import json_to_barescript

# Check if the input path is provided as a command-line argument
if len(sys.argv) < 2:
    print("Usage: python convert_json_to_barescript_from_directory.py <input_path>")
    sys.exit(1)

input_path = sys.argv[1]
output_path = os.path.join(input_path + "_py")

os.makedirs(output_path, exist_ok=True)
json_list = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.endswith('.json')]

print("Converting JSON files to Barescript...")
# Iterate over each JSON file in the list
for json_file in json_list:
    # Define the output file path by replacing the ".json" extension with ".py"
    output_file = os.path.join(output_path, os.path.basename(json_file).replace(".json", ".py"))
    
    # Run the JSON to Barescript conversion for the current file
    # The `reportfunc=False` argument disables additional reporting
    json_to_barescript.run(json_file, output_file, reportfunc=False)

print("Your converted JSON files are in the directory: " + output_path)
print("done")