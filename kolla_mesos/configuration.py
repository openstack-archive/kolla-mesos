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

import json
import os.path

from oslo_config import cfg
from oslo_log import log as logging
import yaml

from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils

LOG = logging.getLogger()
CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('kolla', 'kolla_mesos.config.zookeeper')


def write_variables_zookeeper(zk, variables, base_node=None, overwrite=True):
    if base_node is None:
        base_node = os.path.join('kolla', CONF.kolla.deployment_id)
    filter_out = ['groups', 'hostvars', 'kolla_config',
                  'inventory_hostname']
    for var in variables:
        if (var in filter_out):
            LOG.debug('Var "%s" with value "%s" is filtered out' %
                      (var, variables[var]))
            continue
        var_value = variables[var]
        if isinstance(variables[var], dict):
            var_value = json.dumps(variables[var])
        var_path = os.path.join(base_node, 'variables', var)
        if not overwrite and zk.exists(var_path):
            LOG.debug('NOT Updating "%s" node in zookeeper(overwite=False).',
                      var_path)
            return
        zk.ensure_path(var_path)
        zk.set(var_path, "" if var_value is None else var_value)
        LOG.debug('Updated "%s" node in zookeeper.' % var_path)


def get_start_config(config_dir, jinja_vars):
    start_conf = os.path.join(config_dir,
                              'common/kolla-start-config.json')
    # override container_config_directory
    cont_conf_dir = 'zk://%s' % (CONF.zookeeper.host)
    jinja_vars['container_config_directory'] = cont_conf_dir
    jinja_vars['deployment_id'] = CONF.kolla.deployment_id
    kolla_config = jinja_utils.jinja_render(start_conf, jinja_vars)
    kolla_config = kolla_config.replace('"', '\\"').replace('\n', '')
    return kolla_config


def write_common_config_to_zookeeper(config_dir, zk, jinja_vars, overwrite=True):
    # 1. At first write global tools to ZK. FIXME: Make it a common profile
    conf_path = os.path.join(config_dir, 'common',
                             'common_config.yml.j2')
    common_cfg = yaml.load(jinja_utils.jinja_render(conf_path, jinja_vars))
    common_node = os.path.join('kolla', 'common')
    for script in common_cfg:
        script_node = os.path.join(common_node, script)
        if not overwrite and zk.exists(script_node):
            LOG.debug('NOT Updating "%s" node in zookeeper(overwite=False).',
                      script_node)
            continue

        zk.ensure_path(script_node)
        source_path = common_cfg[script]['source']
        src_file = source_path
        if not source_path.startswith('/'):
            src_file = file_utils.find_file(source_path)
        with open(src_file) as fp:
            content = fp.read()
        zk.set(script_node, content)
