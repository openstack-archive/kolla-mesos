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
import logging

from kolla_mesos.common import cli_utils
from kolla_mesos import service


class Run(command.Command):
    """Run a service."""

    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = super(Run, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        service.run_service(parsed_args.service,
                            self.app.options.service_dir)


class Kill(command.Command):
    """Kill a service."""

    log = logging.getLogger(__name__)

    def take_action(self, parsed_args):
        self.log.info('sending greeting')
        self.log.debug('debugging')
        self.app.stdout.write('hi!\n')


class Show(show.ShowOne):
    """Show the live status of the task or service."""

    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = super(Show, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        ser = service.get_service(parsed_args.service)
        return cli_utils.dict2columns(ser, id_col='service')


class List(lister.Lister):
    """List all deployed services for this deployment_id."""

    log = logging.getLogger(__name__)

    def take_action(self, parsed_args):
        apps = service.list_services()
        values = []
        cols = ('service', 'instances', 'tasksUnhealthy', 'tasksHealthy',
                'tasksRunning', 'tasksStaged', 'version')
        for app in apps:
            values.append([app[field] for field in cols])
        return (cols, values)


class Log(command.Command):
    """Dump the logs for this task or service."""

    log = logging.getLogger(__name__)

    def take_action(self, parsed_args):
        self.log.info('sending greeting')
        self.log.debug('debugging')
        self.app.stdout.write('hi!\n')
