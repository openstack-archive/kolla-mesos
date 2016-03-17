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

import os.path

from oslo_config import cfg
from oslo_log import log

from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import zk_utils
from kolla_mesos import configuration

CONF = cfg.CONF
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
