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

import collections
import json
import os.path

from oslo_config import cfg
from oslo_log import log as logging
from six.moves import configparser
from six.moves import cStringIO
import yaml

from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils

LOG = logging.getLogger()
CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')


class File(object):
    def __init__(self, conf, name, service_name):
        self._conf = conf
        self._name = name
        self._service_name = service_name
        self.base_dir = os.path.abspath(file_utils.find_base_dir())

    def merge_ini_files(self, source_files):
        config_p = configparser.ConfigParser()
        for src_file in source_files:
            if not src_file.startswith('/'):
                src_file = os.path.join(self.base_dir, src_file)
            if not os.path.exists(src_file):
                LOG.warning('path missing %s' % src_file)
                continue
            config_p.read(src_file)
        merged_f = cStringIO()
        config_p.write(merged_f)
        return merged_f.getvalue()

    def write_to_zookeeper(self, zk, base_node):
        dest_node = os.path.join(base_node, self._service_name,
                                 'files', self._name)
        zk.ensure_path(dest_node)
        if isinstance(self._conf['source'], list):
            content = self.merge_ini_files(self._conf['source'])
        else:
            src_file = self._conf['source']
            if not src_file.startswith('/'):
                src_file = file_utils.find_file(src_file)
            with open(src_file) as fp:
                content = fp.read()
        zk.set(dest_node, content)


class Command(object):
    def __init__(self, conf, name, service_name):
        self._conf = conf
        self._name = name
        self._service_name = service_name

    def write_to_zookeeper(self, zk, base_node):
        for fn in self._conf.get('files', []):
            fo = File(self._conf['files'][fn], fn, self._service_name)
            fo.write_to_zookeeper(zk, base_node)


class Runner(object):
    def __init__(self, conf):
        self._conf = conf
        self.base_dir = os.path.abspath(file_utils.find_base_dir())
        self.type_name = None
        self._enabled = self._conf.get('enabled', True)
        if not self._enabled:
            LOG.warn('Service %s disabled', self._conf['name'])

    def _list_commands(self):
        if 'service' in self._conf:
            yield 'daemon', self._conf['service']['daemon']
        for key in self._conf.get('commands', []):
            yield key, self._conf['commands'][key]

    def write_to_zookeeper(self, zk, base_node):
        if not self._enabled:
            return
        for cmd_name, cmd_conf in self._list_commands():
            cmd = Command(cmd_conf, cmd_name, self._conf['name'])
            cmd.write_to_zookeeper(zk, base_node)

        dest_node = os.path.join(base_node, self._conf['name'])
        zk.ensure_path(dest_node)
        try:
            zk.set(dest_node, json.dumps(self._conf))
        except Exception as te:
            LOG.error('%s=%s -> %s' % (dest_node, self._conf, te))

    def _apply_service_def(self, app_def):
        """Apply the specifics from the service definition."""

    def generate_deployment_files(self, kolla_config, jinja_vars, temp_dir):
        if not self._enabled:
            return
        _, proj, service = self._conf['name'].split('/')
        values = {
            'service_name': self._conf['name'],
            'chronos_service_id': self._conf['name'].replace('/', '-'),
            'kolla_config': kolla_config,
            'zookeeper_hosts': CONF.zookeeper.host,
            'private_interface': CONF.network.private_interface,
            'public_interface': CONF.network.public_interface,
        }

        app_file = os.path.join(self.base_dir, 'services',
                                'default.%s.j2' % self.type_name)
        content = jinja_utils.jinja_render(app_file, jinja_vars,
                                           extra=values)
        app_def = yaml.load(content)
        self._apply_service_def(app_def)
        dest_file = os.path.join(temp_dir, proj,
                                 '%s.%s' % (service, self.type_name))
        file_utils.mkdir_p(os.path.dirname(dest_file))
        LOG.info(dest_file)
        with open(dest_file, 'w') as f:
            f.write(json.dumps(app_def, indent=2))


def dict_update(d, u):
    if not isinstance(u, collections.Mapping):
        return u

    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            d[k] = dict_update(d.get(k, {}), v)
        else:
            d[k] = u[k]
    return d


class MarathonApp(Runner):
    def __init__(self, conf):
        super(MarathonApp, self).__init__(conf)
        self.type_name = 'marathon'

    def _apply_service_def(self, app_def):
        """Apply the specifics from the service definition."""

        # 1. get docker options from "container"
        dock_opts = ('image', 'network', 'portMappings',
                     'privileged', 'parameters')
        if 'container' in self._conf:
            for opt in dock_opts:
                if opt not in self._conf['container']:
                    continue
                if 'docker' not in app_def['container']:
                    app_def['container']['docker'] = {}
                app_def['container']['docker'][opt] = dict_update(
                    app_def['container']['docker'].get(opt),
                    self._conf['container'][opt])

        # 2. get remaining options from "container" and place into container
        for opt in self._conf.get('container', {}):
            if opt not in dock_opts and opt != 'docker':
                app_def['container'][opt] = dict_update(
                    app_def['container'].get(opt),
                    self._conf['container'][opt])

        # 3. get options from "service"
        ignore_opts = ('daemon', )
        for opt in self._conf.get('service', {}):
            if opt not in ignore_opts:
                app_def[opt] = dict_update(app_def.get(opt),
                                           self._conf['service'][opt])


class ChronosTask(Runner):
    def __init__(self, conf):
        super(ChronosTask, self).__init__(conf)
        self.type_name = 'chronos'

    def _apply_service_def(self, task_def):
        """Apply the specifics from the service definition."""

        # now merge in the service definition specifics.
        task_def['container'] = dict_update(
            task_def['container'], self._conf.get('container', {}))

        if self._conf.get('task') is None:
            return
        for key in self._conf['task']:
            if key is 'env':
                for env in self._conf['task']['env']:
                    self.set_env(key, self._conf['task']['env'][env],
                                 task_def['environmentVariables'])
            else:
                task_def[key] = dict_update(
                    task_def[key], self._conf['task'][key])

    def set_env(self, key, value, chronos_env):
        for cenv in chronos_env:
            if cenv['name'] == key:
                cenv['value'] = value
                return
        chronos_env.append({"name": key, "value": value})
