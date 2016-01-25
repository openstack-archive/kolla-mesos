#!/usr/bin/env python

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
"""
usage: show_tasks.py [-h] [--id ID] [--list_ids]

Show tasks for a deployment. If there is only one deployment id, an id does
not have to be specified.

optional arguments:
  -h, --help      show this help message and exit
  --id ID         show tasks for this deployment id
  --list_ids, -l  list out the current deployment ids
"""
import argparse
import os
import sys
import traceback
import yaml

from kolla_mesos.common import cli_utils
from kolla_mesos.common import file_utils
from kolla_mesos.common import zk_utils

CONFIG_SUFFIX = '_config.yml.j2'
DEPLOY_ID_TAG = '{{ deployment_id }}'


def get_deploy_id(ids):
    deploy_id = ''
    if ids:
        deploy_id = ids[0]
    print('Deployment id: %s' % deploy_id)
    return deploy_id


def list_ids(ids):
    out = '['
    comma = ''
    for deploy_id in ids:
        out += comma + deploy_id
        comma = ', '
    print(out + ']')


def validate_input(args_ids, ids):
    if not ids:
        print('Error: No deployment ids exist.')
        sys.exit(1)
    if args_ids:
        if args_ids[0] not in ids:
            print("Error: Deployment id %s doesn't exist in " % args_ids +
                  'the current set of ids: %s' % ids)
            sys.exit(1)
    elif len(ids) > 1:
        print('Error: Multiple deployment ids exist: %s.\n' % ids +
              'Use %s --id deployment_id.' % sys.argv[0])
        sys.exit(1)


def get_deployment_ids():
    ids = []
    with zk_utils.connection() as zk:
        children = zk.get_children('/kolla')
        for child in children:
            if child not in ['groups', 'variables', 'common',
                             'config', 'commands']:
                ids.append(child)
    return ids


def get_tasks(deploy_id):
    """Get list of tasks

    Reads through all the kolla mesos services config files and
    parses the requirements and resister options.

    Returns a dictionary of all the values registered by tasks
    {
    taskpath1: {
      'requires': [require1, require2...]
      'register': register_path
      }
    }

    taskpath examples -
      'keystone/keystone/setup',
      'keystone/keystone_ansible_tasks/create_database',
    """
    tasks = {}
    config_dir = os.path.join(file_utils.find_base_dir(), 'config')
    for root, _, files in os.walk(config_dir):
        for name in files:
            if CONFIG_SUFFIX not in name:
                continue
            fpath = os.path.join(root, name)
            cfg_string = ''
            with open(fpath, 'r') as cfg_file:
                for line in cfg_file:
                    # comment out lines that cause yaml load to fail
                    if line.startswith('{%'):
                        line = '# ' + line
                    else:
                        # add the deployment_id to the path
                        line = line.replace(DEPLOY_ID_TAG, deploy_id)
                    # avoid yaml/j2 conflicts
                    line = line.replace('{{ ', '<<')
                    line = line.replace(' }}', '>>')
                    cfg_string += line

            try:
                cfg = yaml.load(cfg_string)
            except Exception:
                print('exception processing file: %s\n ' % fpath +
                      'yaml: %s' % cfg_string)
                raise Exception(traceback.format_exc())
            if 'commands' not in cfg:
                continue
            commands = cfg['commands']
            for group, group_info in commands.items():
                for role, role_info in group_info.items():
                    for cmd, cmd_info in role_info.items():
                        task_name = '/%s/%s/%s' % (group, role, cmd)
                        tasks[task_name] = {}
                        if 'register' in cmd_info:
                            tasks[task_name]['register'] = cmd_info['register']
                        if 'requires' in cmd_info:
                            tasks[task_name]['requires'] = cmd_info['requires']
    return tasks


def get_status(tasks):
    """Get status from zookeeper

    Returns the status of for each task
    {
        task1: {
            'register': (register_path, reg_status)
            'requirements': {
                reqt1_path: reqt_status
                reqt2_path: reqt_status
                ...
            }
        }

    Where:
        reg_status = 'done', 'running', 'waiting'
        reqt_status = '', 'done'
    """
    status = {}
    with zk_utils.connection() as zk:
        # get status of requirements
        for task, info in tasks.items():
            status[task] = {}
            if 'requires' in info:
                status[task]['requirements'] = {}
                for path in info['requires']:
                    reqt_status = ''
                    if zk.exists(path):
                        reqt_status = 'done'
                    status[task]['requirements'][path] = reqt_status

        # get status of registrations
        for task, info in tasks.items():
            if 'register' in info:
                status[task]['register'] = {}
                reg_status = 'NOT DONE'
                reg_path = info['register']
                if zk.exists(reg_path):
                    reg_status = 'done'
                elif 'requires' in info:
                    all_done = True
                    for path in info['requires']:
                        if not status[task]['requirements'][path]:
                            all_done = False
                            break
                    if not all_done:
                        reg_status = 'waiting'

                status[task]['register'] = (reg_path, reg_status)
    return status


def print_status(status):
    tasknames = sorted(status)
    header = ['Task', 'Register (/kolla/variables/)', 'Reg Sts',
              "Reqts (/kolla/variables/)", 'Reqt Sts']
    rows = []
    for taskname in tasknames:
        reg_path = ''
        reg_status = ''
        if 'register' in status[taskname]:
            reg_path, reg_status = status[taskname]['register']
            reg_path = clean_path(reg_path)

        if 'requirements' in status[taskname]:
            reqts = status[taskname]['requirements']
            tname = taskname
            reqt_paths = sorted(reqts)
            for reqt_path in reqt_paths:
                reqt_status = reqts[reqt_path]
                reqt_path = clean_path(reqt_path)
                rows.append((tname, reg_path, reg_status,
                             reqt_path, reqt_status))
                tname = ''
                reg_path = ''
                reg_status = ''
        else:
            rows.append((taskname, reg_path, reg_status,
                         '', ''))
    cli_utils.lister(header, rows, align='l')


def clean_path(path):
    """clean path to reduce output clutter

    The path is either:
        /kolla/variables/.../.done (older version) or
        /kolla/deployment_id/variables/.../.done

    This will remove edit down the path to just the string between
    'variables' and '.done'.
    """
    if 'variables/' in path:
        path = path.rsplit('variables/', 1)[1]
    if '/.done' in path:
        path = path.rsplit('/.done', 1)[0]
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.description = (
        'Show tasks for a deployment.\n' +
        'If there is only one deployment id, an id does not have to be ' +
        'specified.')

    parser.add_argument('--id', nargs=1,
                        help='show tasks for this deployment id')
    parser.add_argument('--list_ids', '-l', action='store_true',
                        help='list out the current deployment ids')
    args = parser.parse_args()

    ids = get_deployment_ids()

    if args.list_ids:
        list_ids(ids)
        sys.exit(0)

    validate_input(args.id, ids)

    deploy_id = get_deploy_id(args.id or ids)

    tasks = get_tasks(deploy_id)
    status = get_status(tasks)
    print_status(status)


if __name__ == '__main__':
    main()
