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
Print out a table showing all the kolla-mesos tasks and their status
"""
from kolla_mesos.common import cli_utils
from kolla_mesos.common import file_utils
from kolla_mesos.common import zk_utils

import os
import yaml

CONFIG_SUFFIX = '_config.yml.j2'


def get_tasks():
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
    for root, _, files in os.walk(file_utils.find_base_dir()):
        for name in files:
            if CONFIG_SUFFIX not in name:
                continue
            fpath = os.path.join(root, name)
            cfg_string = ''
            with open(fpath, 'r') as cfg_file:
                # comment out lines that cause yaml load to fail
                for line in cfg_file:
                    if line.startswith('{%'):
                        line = '# ' + line
                    cfg_string += line

            cfg = yaml.load(cfg_string)
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
    path = path.replace('/.done', '')
    path = path.replace('/kolla/variables/', '')
    return path


def main():
    tasks = get_tasks()
    status = get_status(tasks)
    print_status(status)


if __name__ == '__main__':
    main()
