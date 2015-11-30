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


CHRONOS_URL = '{}:4400'.format(network_utils.get_ip_address())

CONF = cfg.CONF
chronos_opts = [
    cfg.StrOpt('host',
               default=CHRONOS_URL,
               help='Chronos connection URL (host:port)'),
    cfg.IntOpt('timeout',
               default=5,
               help='Timeout for the request to the Chronos API')
]
chronos_opt_group = cfg.OptGroup(name='chronos',
                                 title='Options for Chronos')
CONF.register_group(chronos_opt_group)
CONF.register_cli_opts(chronos_opts, chronos_opt_group)
CONF.register_opts(chronos_opts, chronos_opt_group)
