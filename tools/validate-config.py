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
import yaml

from kolla_mesos.common import jinja_utils

CNF_FIELDS = ('source', 'dest', 'owner', 'perm')
CMD_FIELDS = ('daemon', 'run_once', 'requires', 'command', 'env', 'register',
              'delay', 'retries')
BASE_PATH = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), '..')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('input', nargs='*')
    return p.parse_args()


def validate_config(conf):
    for file in conf:
        for key in conf[file]:
            assert key in CNF_FIELDS, '%s not in %s' % (key, CNF_FIELDS)
        srcs = conf[file]['source']
        if isinstance(srcs, str):
            srcs = [srcs]
        for src in srcs:
            file_path = os.path.join(BASE_PATH, src)
            if not file_path.startswith('/etc'):
                assert os.path.exists(file_path), '%s missing' % file_path


def validate_command(cmds):
    for cmd in cmds:
        for key in cmds[cmd]:
            assert key in CMD_FIELDS, '%s not in %s' % (key, CMD_FIELDS)


def validate(group, role):
    conf_path = os.path.join(BASE_PATH, 'config', group,
                             '%s_config.yml.j2' % group)
    mini_vars = {'cinder_volume_driver': 'lvm'}
    cnf = yaml.load(jinja_utils.jinja_render(conf_path, mini_vars))
    validate_command(cnf['commands'][group][role])
    if role not in cnf['config'][group]:
        print('WARN: no config for role %s in group %s' % (role, group))
    else:
        validate_config(cnf['config'][group][role])


def main():
    args = parse_args()
    logging.basicConfig()
    res = 0

    for filename in args.input:
        with open(filename) as fd:
            try:
                group = None
                role = None
                js = json.load(fd)
                if 'marathon' in filename:
                    group = js['env']['KOLLA_GROUP']
                    role = js['env']['KOLLA_ROLE']
                else:
                    for env in js['environmentVariables']:
                        if env['name'] == 'KOLLA_GROUP':
                            group = env['value']
                        elif env['name'] == 'KOLLA_ROLE':
                            role = env['value']

                validate(group, role)
            except ValueError as error:
                res = 1
                logging.error('%s failed validation: %s',
                              filename, error)

    sys.exit(res)

if __name__ == '__main__':
    main()
