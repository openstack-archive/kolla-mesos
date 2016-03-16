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

from kolla_mesos import cleanup
from kolla_mesos.common import cli_utils
from kolla_mesos import deployment
from kolla_mesos import service

CONF = cfg.CONF
CONF.import_opt('workers', 'kolla_mesos.config.multiprocessing_cli')
LOG = log.getLogger(__name__)


class Run(command.Command):
    """Run the services in the configured profile."""

    def take_action(self, parsed_args):
        deployment.run_deployment()
        deployment.write_openrc('%s-openrc' % CONF.kolla.deployment_id)


class Kill(command.Command):
    """Kill all the running services."""

    def take_action(self, parsed_args):
        for serv in service.list_services():
            service.kill_service(serv['service'])


class Cleanup(command.Command):
    """Delete all created resources."""

    def take_action(self, parsed_args):
        cleanup.cleanup()


class Show(show.ShowOne):
    """Show the deployment configuration."""

    def take_action(self, parsed_args):
        conf_opts = deployment.get_deployment()
        return cli_utils.dict2columns(conf_opts, id_col='deployment_id')


class List(lister.Lister):
    """List all existing deployments."""

    def take_action(self, parsed_args):
        cols = ['Deployment ID']
        ids = deployment.list_deployments()
        values = [[id] for id in ids]
        return cols, values
