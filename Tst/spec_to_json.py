#!/usr/bin/env python

import json
import sys

sys.path.append('../Ccs')
import ccs_function_lib as cfl


def run(specfile, gen_cmd, save_json):
    tmp = json.load(open('tst_template_empty.json', 'r'))
    jspec = tmp.copy()
    specs = open(specfile, 'r').read().split('\n')

    name, descr, spec_version_entry, sw_version_entry = specs[1].split('|')
    spec_version = spec_version_entry.split('version: ')[-1]
    sw_version = sw_version_entry.split('IASW-')[-1]

    jspec['_name'] = name
    jspec['_description'] = descr
    jspec['_spec_version'] = spec_version
    jspec['_sw_version'] = sw_version
    jspec['_primary_counter_locked'] = False

    steps = jspec['sequences'][0]['steps']
    step_temp = steps[0].copy()
    steps = []

    for step in specs[4:]:

        if step.count('|') != 3:
            continue

        n, descr, ver, _ = step.split('|')

        if not n.lower().startswith(('step', 'comment')):
            continue

        if n.lower() == 'comment':
            step = steps[-1]
            step['_step_comment'] = descr
            continue

        step_num = n.replace('Step ', '')
        step_temp['_step_number'] = step_num
        step_temp['_primary_counter'] = int(step_num.split('.')[0])
        step_temp['_secondary_counter'] = int(step_num.split('.')[1])
        step_temp['_description'] = descr
        step_temp['_verification_description'] = ver

        if gen_cmd and ('TC(' in descr):
            try:
                i = descr.index('TC(') + 3
                j = descr.index(')', i)
                st, sst = map(int, descr[i:j].split(','))
                cmd = cfl.get_tc_descr_from_stsst(st, sst)
                if len(cmd) > 1:
                    for c in cmd:
                        if c in descr:
                            _cmd = c
                            break
                        _cmd = cmd[0]
                else:
                    _cmd = cmd[0]
                cmdtxt = cfl.make_tc_template(_cmd, add_parcfg=True)
            except Exception as err:
                print(err)
        else:
            cmdtxt = ''

        step_temp['_command_code'] = cmdtxt

        steps.append(step_temp.copy())

    jspec['sequences'][0]['steps'] = steps
    if save_json:
        json.dump(jspec, open(specfile + '.json', 'w'), indent=4)
    else:
        json_data = json.dumps(jspec)
        return jspec


if __name__ == "__main__":
    if '--nocmd' in sys.argv:
        gen_cmd = False
        sys.argv.remove('--nocmd')
    else:
        gen_cmd = True

    specfile = sys.argv[1]
    save = True
    run(specfile, gen_cmd, save)
