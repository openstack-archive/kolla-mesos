#!/usr/bin/python

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import json
import logging
import os.path
import sys

from kolla_mesos import service_definition

# Some roles are depending on some global variables to be included in
# configuration. The example are Neutron plugins - definitions of
# neutron-openvswitch-agent and neutron-linuxbridge exist only when the
# neutron_plugin_agent variable is set properly.
# ROLE_VARS_MAP dictionary should have the following format:
# {
#     '<role>': {
#         '<variable_name>': 'variable_value'
#         [...]
#      },
#      [...]
# }
_OVS_VARS = {
    'neutron_plugin_agent': 'openvswitch'
}
ROLE_VARS_MAP = {
    'neutron-linuxbridge-agent': {
        'neutron_plugin_agent': 'linuxbridge'
    },
    'neutron-openvswitch-agent': _OVS_VARS,
    'openvswitch-db': _OVS_VARS,
    'openvswitch-vswitchd': _OVS_VARS
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('input', nargs='*')
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig()
    res = 0

    deps = {}
    for filename in args.input:
        mini_vars = {'cinder_volume_driver': 'lvm',
                     'enable_memcached': 'yes',
                     'deployment_id': 'test'}
        role = filename.replace('.yml.j2', '')
        role_vars = ROLE_VARS_MAP.get(role, {})
        mini_vars.update(role_vars)

        ser_dir = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])),
                               '..', 'services')
        ser_name = '/'.join(filename.split('/')[-2:]).replace('.yml.j2', '')
        service_definition.validate(ser_name, ser_dir,
                                    variables=mini_vars, deps=deps)
    print(json.dumps(deps, indent=2))
    # validate the deps
    for task in deps:
        if 'registered_by' not in deps[task]:
            res = 1
            logging.error('%s not registered' % task)
    sys.exit(res)

if __name__ == '__main__':
    main()
