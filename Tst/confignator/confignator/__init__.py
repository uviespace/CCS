from . import config
from . import open_doc

# make wrapper functions
get_config = config.get_config
get_option = config.get_option
get_bool_option = config.get_bool_option
save_option = config.save_option
documentation = open_doc.open_documentation_in_firefox
set_own_log_file_path = config.set_own_log_file_path
