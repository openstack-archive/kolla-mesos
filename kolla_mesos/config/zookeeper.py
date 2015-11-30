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
zookeeper_opts = [
    cfg.StrOpt('host',
               default='localhost:2181',
               help='ZooKeeper connection URL (host:port)')
]
zookeeper_opt_group = cfg.OptGroup(name='zookeeper',
                                   title='Options for ZooKeeper')
CONF.register_group(zookeeper_opt_group)
CONF.register_cli_opts(zookeeper_opts, zookeeper_opt_group)
CONF.register_opts(zookeeper_opts, zookeeper_opt_group)
