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
import re
import socket
import sys
import yaml

from kolla_mesos.common import jinja_utils

CNF_FIELDS = ('source', 'dest', 'owner', 'perm')
CMD_FIELDS = ('run_once', 'dependencies', 'command', 'env',
              'delay', 'retries', 'files')
BASE_PATH = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), '..')
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


def validate_config(filename, conf):
    for file in conf:
        for key in conf[file]:
            assert key in CNF_FIELDS, '%s: %s not in %s' % (filename,
                                                            key, CNF_FIELDS)
        srcs = conf[file]['source']
        if isinstance(srcs, str):
            srcs = [srcs]
        for src in srcs:
            file_path = os.path.join(BASE_PATH, src)
            if not file_path.startswith('/etc'):
                assert os.path.exists(file_path), '%s missing' % file_path


def validate_command(filename, cmd, cmd_info, deps, role):
    for key in cmd_info:
        assert key in CMD_FIELDS, '%s not in %s' % (key, CMD_FIELDS)

    reg = '%s/%s' % (role, cmd)
    reqs = cmd_info.get('dependencies', [])
    if reg not in deps:
        deps[reg] = {'waiters': {}}
    deps[reg]['registered_by'] = cmd
    deps[reg]['name'] = cmd
    deps[reg]['run_by'] = filename
    for req in reqs:
        scope = req.get('scope', 'global')
        if scope == 'global':
            req_path = req['path']
        elif scope == 'local':
            req_path = os.path.join(socket.gethostname(), req_path)
        if req_path not in deps:
            deps[req_path] = {'waiters': {}}
        deps[req_path]['waiters'][cmd] = reg
    if 'files' in cmd_info:
        validate_config(filename, cmd_info['files'])


def validate(filename, deps):
    mini_vars = {'cinder_volume_driver': 'lvm',
                 'enable_memcached': 'yes',
                 'deployment_id': 'test',
                 'controller_nodes': '1',
                 'compute_nodes': '1'}
    role = filename.replace('.yml.j2', '')
    role_vars = ROLE_VARS_MAP.get(role, {})
    mini_vars.update(role_vars)

    cnf = yaml.load(jinja_utils.jinja_render(filename, mini_vars))

    def get_commands():
        for cmd in cnf.get('commands', {}):
            yield cmd, cnf['commands'][cmd]
        if 'service' in cnf:
            yield 'daemon', cnf['service']['daemon']

    _, group, role = cnf['name'].split('/')

    for cmd, cmd_info in get_commands():
        validate_command(filename, cmd, cmd_info, deps, role)


def main():
    args = parse_args()
    logging.basicConfig()
    res = 0

    deps = {}
    for filename in args.input:
        validate(filename, deps)
    print(json.dumps(deps, indent=2))
    # validate the deps
    for task in deps:
        task = re.sub(r'<hostname>', socket.gethostname(), task)
        if 'registered_by' not in deps[task]:
            res = 1
            logging.error('%s not registered' % task)
    sys.exit(res)

if __name__ == '__main__':
    main()
