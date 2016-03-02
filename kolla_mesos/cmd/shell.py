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

import logging
import os.path
import sys

from cliff import app
from cliff import commandmanager
from oslo_config import cfg

from kolla_mesos.common import file_utils
from kolla_mesos.common import utils

VERSION = '1.0'
CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')

cli_opts = [
    cfg.StrOpt('service-dir',
               default=utils.env(
                   'KM_SERVICE_DIR', default=os.path.join(
                       file_utils.find_base_dir(), 'services')),
               help='Directory with services, (Env: KM_SERVICE_DIR)'),
]
CONF.register_cli_opts(cli_opts)


# TODO(apavlov): implement custom --help
class KollaMesosShell(app.App):
    def __init__(self):
        super(KollaMesosShell, self).__init__(
            description='Kolla-mesos command-line interface',
            version=VERSION,
            command_manager=commandmanager.CommandManager('kolla_mesos.cli'),
            deferred_help=True,
            )

    def initialize_app(self, argv):
        if self.options.verbose_level > 1:
            CONF.log_opt_values(logging.getLogger('kolla-mesos'),
                                logging.DEBUG)


def _separate_args(argv):
        config_args = []
        command_args = argv[:]
        while command_args:
            if command_args[0].startswith('-'):
                if len(command_args) == 1 or command_args[1].startswith('-'):
                    config_args.append(command_args[0])
                    command_args.pop(0)
                else:
                    config_args.extend(command_args[:2])
                    command_args = command_args[2:]
            else:
                break
        return config_args, command_args


def main(argv=sys.argv[1:]):
    config_args, command_args = _separate_args(argv)

    need_help = ('help' in config_args or '-h' in config_args or
                 '--help' in config_args)
    if need_help:
        return KollaMesosShell().run(['help'])

    command_list = ('--version', '-v', '--verbose', '-q', '--quiet', '--debug')
    for com in command_list:
        if com in config_args:
            config_args.remove(com)
            command_args.insert(0, com)

    CONF(config_args, project='kolla-mesos')
    return KollaMesosShell().run(command_args)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
