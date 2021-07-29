#!/usr/bin/env python

import datetime
import json
import sys

jfile = sys.argv[1]
# = 'IASW-FFT-1-TS-1.csv.json'

data = json.load(open(jfile, 'r'))
date = datetime.datetime.now().strftime('%Y-%m-%d')

script = ''

script += '#--------------------------------------------\n'
script += '# ' + data['_name'] + '\n'
script += '# ' + data['_description'] + '\n'
script += '# Version: ' + data['_version'] + '\n'
script += '# Author: UVIE\n# Date: {}\n'.format(date)
script += '#--------------------------------------------\n\n\n'

script += '# Precond.\n# {}\n\n\n'.format(data['_precon_descr'])

for step in data['sequences'][0]['steps']:
    comment = '# COMMENT: {}\n'.format(step['_step_comment'].strip()) if step['_step_comment'] != '' else ''

    txt = '# STEP {}\n' \
          '# {}\n' \
          '{}\n' \
          '# VERIFICATION: {}\n{}\n\n'.format(step['_step_number'], step['_description'].strip(), step['_command_code'].strip(), step['_verification_description'].strip(), comment)

    script += txt

script += '# Postcond.\n# {}\n'.format(data['_postcon_descr'])

outpath = '/'.join(jfile.split('/')[:-1]) + '/'
outfile = outpath + data['_name'] + '-' + '-'.join(data['_version'].split('-')[-2:]) + '.py'

with open(outfile, 'w') as fd:
    fd.write(script)
