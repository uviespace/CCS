# Define the PRIMARY_HEADER structure
import ctypes

PRIMARY_HEADER = [
    ("PKT_VERS_NUM", ctypes.c_uint16, 3),
    ("PKT_TYPE", ctypes.c_uint16, 1),
    ("SEC_HEAD_FLAG", ctypes.c_uint16, 1),
    ("APID", ctypes.c_uint16, 11),
    ("SEQ_FLAGS", ctypes.c_uint16, 2),
    ("PKT_SEQ_CNT", ctypes.c_uint16, 14),
    ("PKT_LEN", ctypes.c_uint16, 16)
]

TC_SECONDARY_HEADER = [
    ("PUS_VERSION", ctypes.c_uint8, 4),
    ("ACK", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("SOURCE_ID", ctypes.c_uint16, 16)
]

def hex_to_primary_header(hex_string):

    print(sum(field[2] for field in PRIMARY_HEADER + TC_SECONDARY_HEADER))

    # Convert hex string to a binary string
    binary_str = bin(int(hex_string, 16))[2:].zfill(sum(field[2] for field in PRIMARY_HEADER + TC_SECONDARY_HEADER))
    
    binary_str = binary_str #"{:0b}".format(binary_str)
    print(hex_string)
    print(int(hex_string, 16))
    print(binary_str)
    print(len(binary_str))
    print(binary_to_hex(binary_str))

    # Dictionary to store the parsed data
    header_data = {}

    # Initialize the start index
    current_bit = 0

    # Parse each field according to its bit length
    for field_name, field_type, bit_length in PRIMARY_HEADER + TC_SECONDARY_HEADER:
        # Extract the relevant bits for this field
        field_bits = binary_str[current_bit:current_bit + bit_length]
        print(field_bits)
        # Convert the bits to an integer
        field_value = int(field_bits, 2)
        print(field_value)
        # Map it to the appropriate ctypes type
        header_data[field_name] = field_type(field_value).value
        # Move the current bit position
        current_bit += bit_length

    return header_data

def binary_to_hex(binary_str):
    # Convert binary string to an integer
    integer_value = int(binary_str, 2)
    # Convert the integer to a hexadecimal string, removing the '0x' prefix
    hex_string = hex(integer_value)[2:]
    # Zero-pad the hex string to ensure even length for full bytes
    hex_string = hex_string.zfill((len(binary_str) + 3) // 4)
    return hex_string.upper()  # Optional: Convert to uppercase for consistency


message = "1930c01100091903050000" #010002144e"

print(len(message[:22]))
header = hex_to_primary_header(message)

print(header)

# BUG: CCS displays hex message 8 bit too short (remnant of SMILE) or packet_config_ARIEL.py is faulty
# BUG: CCS TC(193,4) faulty description