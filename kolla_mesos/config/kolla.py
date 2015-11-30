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


CONF = cfg.CONF
kolla_opts = [
    cfg.StrOpt('namespace',
               default='kollaglue'),
    cfg.StrOpt('tag',
               default='latest'),
    cfg.StrOpt('base',
               default='centos'),
    cfg.StrOpt('base-tag',
               default='latest'),
    cfg.StrOpt('install-type',
               default='binary'),
    cfg.StrOpt('profile',
               default='default')
]
kolla_opt_group = cfg.OptGroup(name='kolla',
                               title='Options for Kolla Docker images')
CONF.register_group(kolla_opt_group)
CONF.register_cli_opts(kolla_opts, kolla_opt_group)
CONF.register_opts(kolla_opts, kolla_opt_group)
