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
from kolla_mesos import service

CONF = cfg.CONF
LOG = log.getLogger(__name__)


class Run(command.Command):
    """Run a service."""

    def get_parser(self, prog_name):
        parser = super(Run, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        service.run_service(parsed_args.service,
                            CONF.service_dir)


class Kill(command.Command):
    """Kill a service."""

    def get_parser(self, prog_name):
        parser = super(Kill, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        service.kill_service(parsed_args.service)


class Show(show.ShowOne):
    """Show the live status of the task or service."""

    def get_parser(self, prog_name):
        parser = super(Show, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        data = service.get_service(parsed_args.service)
        return cli_utils.dict2columns(data, id_col='service')


class List(lister.Lister):
    """List all deployed services for this deployment_id."""

    def take_action(self, parsed_args):
        apps = service.list_services()
        values = []
        cols = ('service', 'type', 'instances', 'tasksUnhealthy',
                'tasksHealthy', 'tasksRunning', 'tasksStaged', 'version')
        for app in apps:
            values.append([app[field] for field in cols])
        return (cols, values)


class Scale(command.Command):
    """Scale the service."""

    def get_parser(self, prog_name):
        parser = super(Scale, self).get_parser(prog_name)
        parser.add_argument('service')
        parser.add_argument('instances')
        parser.add_argument('--force', action='store_true',
                            default=False)

        return parser

    def take_action(self, parsed_args):
        service.scale_service(parsed_args.service,
                              parsed_args.instances,
                              parsed_args.force)


class Log(command.Command):
    """Dump the logs for this task or service."""

    def get_parser(self, prog_name):
        parser = super(Show, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        self.app.stdout.write(service.get_service_logs(parsed_args.service))


class Snapshot(command.Command):
    """Snapshot the service configuration and deployment file.

    This will produce a tarball that can be later used with
    'kolla-mesos update <service> --snapshot <file>'
    """

    def get_parser(self, prog_name):
        parser = super(Snapshot, self).get_parser(prog_name)
        parser.add_argument('service')
        parser.add_argument('output-dir')
        return parser

    def take_action(self, parsed_args):
        service.snapshot_service(parsed_args.service,
                                 parsed_args.output_dir)


class Update(command.Command):
    """Update the service configuration and deployment file."""

    def get_parser(self, prog_name):
        parser = super(Update, self).get_parser(prog_name)
        parser.add_argument('service')
        return parser

    def take_action(self, parsed_args):
        service.update_service(parsed_args.service, CONF.service_dir)
