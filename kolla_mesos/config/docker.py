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

from kolla_mesos.common import utils


CONF = cfg.CONF
docker_opts = [
    cfg.IntOpt('port',
               default=utils.env('KM_DOCKER_PORT', default=5555),
               help='Docker connection port (Env: KM_DOCKER_PORT)')
]
docker_opt_group = cfg.OptGroup(name='docker',
                                title='Options for Docker')
CONF.register_group(docker_opt_group)
CONF.register_cli_opts(docker_opts, docker_opt_group)
CONF.register_opts(docker_opts, docker_opt_group)
