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

from cliff import lister
from oslo_config import cfg
from oslo_log import log

from kolla_mesos import commands

CONF = cfg.CONF
LOG = log.getLogger(__name__)


def format_output(status):
    cols = ('Command', 'Status', 'Requirements')
    rows = []
    for taskname, info in sorted(status.items()):
        reg_status = info['register'][1] or 'UNKNOWN'

        requirements = []
        reqts = info['requirements']
        for reqt_path, reqt_status in sorted(reqts.items()):
            reqt_path = reqt_path.split(
                'status/')[1] if 'status/' in reqt_path else reqt_path
            if not reqt_status:
                reqt_status = 'UNKNOWN'
            requirements.append('%s:%s' % (reqt_path, reqt_status))

        requirements = '\n'.join(requirements)
        rows.append((taskname, reg_status, requirements))

    return cols, rows


def _clean_path(path):
    if 'status/' in path:
        path = path.split('status/')[1]
    return path


class List(lister.Lister):
    """List all commands and their statuses for this service."""

    def get_parser(self, prog_name):
        parser = super(List, self).get_parser(prog_name)
        parser.add_argument(
            'service',
            nargs='?',
            help='Information for the deployment will be shown if the service '
                 'is not specified'
        )
        return parser

    def take_action(self, parsed_args):
        if parsed_args.service:
            status = commands.get_service_status(
                parsed_args.service, CONF.service_dir)
        else:
            status = commands.get_deployment_status(CONF.service_dir)

        return format_output(status)
