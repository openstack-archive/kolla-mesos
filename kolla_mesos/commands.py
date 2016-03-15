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

import os
import socket
import yaml

from oslo_config import cfg
from oslo_log import log as logging

from kolla_mesos.common import jinja_utils
from kolla_mesos.common import mesos_utils
from kolla_mesos import service_definition
from kolla_mesos.common import zk_utils

LOG = logging.getLogger()
CONF = cfg.CONF

CONF.import_group('kolla', 'kolla_mesos.config.kolla')


def _get_task_from_cmd(role, cmd, cmd_info):
    reg = '/kolla/%s/status/%s/%s' % (CONF.kolla.deployment_id, role, cmd)
    task = {'register': reg, 'requires': []}
    for dep in cmd_info.get('dependencies', []):
        path = dep['path']
        scope = dep.get('scope', 'global')
        if scope == 'global':
            task['requires'].append(
                '/kolla/%s/status/%s' % (CONF.kolla.deployment_id, path))
        elif scope == 'local':
            task['requires'].append(
                '/kolla/%s/status/%s/%s' % (CONF.kolla.deployment_id,
                                            socket.gethostname(),
                                            path))
    return task


def _get_config_tasks(config_path, tasks):
    controller_nodes, compute_nodes, storage_nodes, all_nodes = \
        mesos_utils.get_number_of_nodes()
    mini_vars = {'cinder_volume_driver': 'lvm',
                 'deployment_id': CONF.kolla.deployment_id,
                 'controller_nodes': str(controller_nodes),
                 'compute_nodes': str(compute_nodes),
                 'storage_nodes': str(storage_nodes),
                 'all_nodes': str(all_nodes)}
    config = yaml.load(jinja_utils.jinja_render(config_path, mini_vars))

    def get_commands():
        for cmd in config.get('commands', {}):
            yield cmd, config['commands'][cmd]
        if 'service' in config:
            yield 'daemon', config['service']['daemon']

    _, _, role = config['name'].split('/')
    for cmd, cmd_info in get_commands():
        task_name = '%s/%s' % (role, cmd)
        tasks[task_name] = _get_task_from_cmd(role, cmd, cmd_info)

    return tasks


def get_tasks(config_path):
    """Get list of tasks

    Reads through all the kolla mesos services config files located in
    config_path and parses the requirements and resister options.

    Returns a dictionary of all the values registered by tasks
    {
    taskpath1: {
      'requires': [require1, require2...]
      'register': register_path
      }
    }

    taskpath examples -
      'keystone/keystone/db_sync',
      'keystone/keystone_ansible_tasks/create_database',
    """

    tasks = {}
    if os.path.isfile(config_path):
        _get_config_tasks(config_path, tasks)
    else:
        for root, _, files in os.walk(config_path):
            for name in files:
                if 'default.' in name:
                    continue
                fpath = os.path.join(root, name)
                _get_config_tasks(fpath, tasks)
    return tasks


def get_service_tasks(service_name, service_dir):
    if '/' not in service_name:
            service_name = service_name.replace('-', '/')
    config_path = service_definition.find_service_file(
        service_name, service_dir)
    return get_tasks(config_path)


def get_status(tasks):
    """Get status from zookeeper

    Returns the status for each task
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
            status[task]['requirements'] = {}
            for path in info['requires']:
                reqt_status = ''
                if zk.exists(path):
                    reqt_status, _ = zk.get(path)
                status[task]['requirements'][path] = reqt_status

        # get status of registrations
        for task, info in tasks.items():
            status[task]['register'] = {}
            reg_path = info['register']
            reg_status = ''
            if zk.exists(reg_path):
                reg_status, _ = zk.get(reg_path)

            status[task]['register'] = (reg_path, reg_status)
    return status


def get_service_status(service_name, service_dir):
    tasks = get_service_tasks(service_name, service_dir)
    return get_status(tasks)


def get_deployment_status(service_dir):
    tasks = get_tasks(service_dir)
    return get_status(tasks)
