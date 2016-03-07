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

from oslo_config import cfg

from kolla_mesos.common import network_utils
from kolla_mesos.common import utils

MESOS_URL = 'http://{}:5050'.format(network_utils.get_ip_address())

CONF = cfg.CONF
mesos_opts = [
    cfg.StrOpt('host',
               default=utils.env('KM_MESOS_HOST', default=MESOS_URL),
               help='Mesos connection URL (http://host:port), '
                    '(Env: KM_MESOS_HOST)'),
    cfg.IntOpt('timeout',
               default=5,
               help='Timeout for the request to the Marathon API')
]
mesos_opt_group = cfg.OptGroup(name='mesos',
                               title='Options for Mesos')
CONF.register_group(mesos_opt_group)
CONF.register_cli_opts(mesos_opts, mesos_opt_group)
CONF.register_opts(mesos_opts, mesos_opt_group)
