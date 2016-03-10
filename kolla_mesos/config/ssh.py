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


CONF = cfg.CONF
ssh_opts = [
    cfg.StrOpt('username',
               default=os.getlogin(),
               help='Username to used in cleanup SSH connections')
]
ssh_opt_group = cfg.OptGroup(name='ssh',
                             title='Options for cleanup SSH connections')
CONF.register_group(ssh_opt_group)
CONF.register_cli_opts(ssh_opts, ssh_opt_group)
CONF.register_opts(ssh_opts, ssh_opt_group)
