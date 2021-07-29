#!/usr/bin/env python

import datetime
import json
import sys

jfile = sys.argv[1]
# = 'IASW-FFT-1-TS-1.csv.json'

data = json.load(open(jfile, 'r'))

header = 'Item|Description|Verification|TestResult'
name = '{}|{}|Test spec. version: {}|'.format(data['_name'], data['_description'], data['_version'])
date = 'Date||{}|'.format(datetime.datetime.now().strftime('%Y-%m-%d'))
precond = 'Precond.|{}||'.format(data['_precon_descr'])
postcond = 'Postcond.|{}||'.format(data['_postcon_descr'])
steps = []

for step in data['sequences'][0]['steps']:

    line = 'Step {}|{}|{}|'.format(step['_step_number'], step['_description'], step['_verification_description'])
    steps.append(line)

    if step['_step_comment'] != '':
        comment = 'Comment|{}||'.format(step['_step_comment'])
        steps.append(comment)


outpath = '/'.join(jfile.split('/')[:-1]) + '/'
outfile = outpath + data['_name'] + '-' + '-'.join(data['_version'].split('-')[-2:]) + '.csv_PIPE'

with open(outfile, 'w') as fd:
    buf = '\n'.join([header, name, date, precond] + steps + [postcond])
    buf = buf.replace('_', '\\_')
    fd.write(buf)
