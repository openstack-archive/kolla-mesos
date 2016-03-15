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

from oslo_config import cfg
from oslo_log import log

from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import zk_utils
from kolla_mesos import configuration
from kolla_mesos import service

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('profiles', 'kolla_mesos.config.profiles')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')
LOG = log.getLogger(__name__)


def write_openrc(out_filename):
    """Write an openrc to for convience."""

    base_dir = file_utils.find_base_dir()
    openrc_file = os.path.join(base_dir, 'config', 'openrc.j2')
    needed_vars = jinja_utils.jinja_find_required_variables(openrc_file)
    with zk_utils.connection() as zk:
        variables = configuration.get_variables_from_zookeeper(zk, needed_vars)
        content = jinja_utils.jinja_render(openrc_file, variables)
        with open(out_filename, 'w') as f:
            f.write(content)
        LOG.info('Written OpenStack env to "%s"', out_filename)


def run_deployment():
    for proj in set(getattr(CONF.profiles, CONF.kolla.profile)):
        for fn in os.listdir(os.path.join(CONF.service_dir, proj)):
            if fn.endswith('.j2') and os.path.isfile(fn):
                service.run_service(fn, CONF.service_dir)


def get_deployment():
    conf_opts = {}
    conf_opts['deployment_id'] = CONF.kolla.deployment_id
    conf_opts['profile'] = CONF.kolla.profile
    conf_opts['service_dir'] = CONF.service_dir
    conf_opts['image-name-template'] = '%s/%s-%s-{{ image }}:%s' % (
        CONF.kolla.namespace, CONF.kolla.base, CONF.kolla.install_type,
        CONF.kolla.tag)
    conf_opts['marathon'] = CONF.marathon.host
    conf_opts['mesos'] = CONF.marathon.host.replace('8080', '5050')
    conf_opts['chronos'] = CONF.chronos.host
    conf_opts['zookeeper'] = CONF.zookeeper.host
    if False:
        # TODO(asalkeld) if horizon is running and ready, get the url.
        conf_opts['horizon'] = ''
    return conf_opts
