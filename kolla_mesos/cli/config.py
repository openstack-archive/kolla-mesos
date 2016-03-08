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

from cliff import command
from cliff import lister
from cliff import show
from oslo_config import cfg
from oslo_log import log

from kolla_mesos.common import cli_utils
from kolla_mesos.common import zk_utils

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
LOG = log.getLogger(__name__)


class ConfigList(lister.Lister):
    """List Zookeeper variables."""

    def get_parser(self, prog_name):
        parser = super(ConfigList, self).get_parser(prog_name)
        parser.add_argument('--path',
                            default='/kolla/%s' % CONF.kolla.deployment_id)
        return parser

    def take_action(self, parsed_args):
        dd = zk_utils.list_all(parsed_args.path)
        return (('Path', 'Value'), dd.items())


class ConfigShow(show.ShowOne):
    """Show a Zookeeper variable value."""

    def get_parser(self, prog_name):
        parser = super(ConfigShow, self).get_parser(prog_name)
        parser.add_argument('path')
        return parser

    def take_action(self, parsed_args):
        data = zk_utils.get_one(parsed_args.path)
        return cli_utils.dict2columns(data, id_col='Path')


class ConfigSet(command.Command):
    """Set a Zookeeper variable value."""

    def get_parser(self, prog_name):
        parser = super(ConfigSet, self).get_parser(prog_name)
        parser.add_argument('path')
        parser.add_argument('value')
        return parser

    def take_action(self, parsed_args):
        zk_utils.set_one(parsed_args.path, parsed_args.value)
