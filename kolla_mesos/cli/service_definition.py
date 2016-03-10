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
from cliff import show
from oslo_log import log

from kolla_mesos import service_definition

LOG = log.getLogger(__name__)


class Inspect(show.ShowOne):
    """Show available parameters and info about a service definition."""

    def get_parser(self, prog_name):
        parser = super(Inspect, self).get_parser(prog_name)
        parser.add_argument('service', help='The service name')
        return parser

    def take_action(self, parsed_args):
        info = service_definition.inspect(parsed_args.service,
                                          self.app.options.service_dir)
        columns = []
        data = []
        for col, val in info.items():
            columns.append(col)
            data.append(val)
        return (columns, data)


class Validate(command.Command):
    """Validate the service definition."""

    def get_parser(self, prog_name):
        parser = super(Validate, self).get_parser(prog_name)
        parser.add_argument('service', help='The service name')
        return parser

    def take_action(self, parsed_args):
        service_definition.validate(parsed_args.service,
                                    self.app.options.service_dir,
                                    variables={})
