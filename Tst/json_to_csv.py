#!/usr/bin/env python

import datetime
import json
import os
import sys


def run(jfile, outfile):

    if os.path.isfile(jfile):
        data = json.load(open(jfile, 'r'))
    else:
        data = json.loads(jfile)

    header = 'Item|Description|Verification|TestResult'
    name = '{}|{}|Test spec. version: {}| IASW-{}'.format(data['_name'], data['_description'], data['_spec_version'], data['_iasw_version'])
    # Date from last time the json file was changed + current date
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

    if outfile[-1] == '/':  # If only path is given but no filename
        outfile = outfile + data['_name'] + '-' + '-'.join(data['_spec_version'].split('-')[-2:]) + '.csv_PIPE'

    with open(outfile, 'w') as fd:
        buf = '\n'.join([header, name, date, precond] + steps + [postcond])
        buf = buf.replace('_', '\\_')
        fd.write(buf)


if __name__ == '__main__':
    json_file_path = sys.argv[1]

    if len(sys.argv) > 1:  # If filename is given
        outputfile = sys.argv[2]
    else:  # If no filename is given take the working directory path, filename is used from the json file
        outputfile = os.getcwd() + '/'
        # outputfile = '/'.join(json_file_path[:-len(json_file_path.split('/')[-1])-1]) + '/'  # This would take the json File path

    run(json_file_path, outputfile)
