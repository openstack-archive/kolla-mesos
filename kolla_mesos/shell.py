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
import sys

from cliff import app
from cliff import commandmanager

from kolla_mesos.cli import utils
from kolla_mesos import client

VERSION = '1.0'


class KollaMesosShell(app.App):
    def __init__(self):
        super(KollaMesosShell, self).__init__(
            description='Kolla-mesos command-line interface',
            version=VERSION,
            command_manager=commandmanager.CommandManager('kolla-mesos.cli'),
            deferred_help=True,
            )

        self._set_shell_commands(self._get_commands())

    @staticmethod
    def _get_commands():
        return {}

    def _set_shell_commands(self, commands):
        for k, v in commands.items():
            self.command_manager.add_command(k, v)

    def build_option_parser(self, description, version,
                            argparse_kwargs=None):
        parser = super(KollaMesosShell, self).build_option_parser(
            description, version, argparse_kwargs)

        parser.add_argument(
            '--config-file',
            action='store',
            default=utils.env('KM_CONFIG_FILE', default=None),
            help='Config file for Kolla-Mesos project, (Env: KM_CONFIG_FILE)'
        )
        parser.add_argument(
            '--zookeeper-url',
            action='store',
            default=utils.env('KM_ZOOKEEPER_URL', default=None),
            help='ZooKeeper connection URL, (Env: KM_ZOOKEEPER_URL)'
        )
        parser.add_argument(
            '--mesos-url',
            action='store',
            default=utils.env('KM_MESOS_URL', default=None),
            help='Mesos connection URL, (Env: KM_MESOS_URL)'
        )
        parser.add_argument(
            '--marathon-url',
            action='store',
            default=utils.env('KM_MARATHON_URL', default=None),
            help='Marathon connection URL, (Env: KM_MARATHON_URL)'
        )
        parser.add_argument(
            '--chronos-url',
            action='store',
            default=utils.env('KM_CHRONOS_URL', default=None),
            help='Chronos connection URL, (Env: KM_CHRONOS_URL)'
        )

        return parser

    def configure_logging(self):
        log_lvl = logging.DEBUG if self.options.debug else logging.WARNING
        logging.basicConfig(
            format="%(levelname)s (%(module)s) %(message)s",
            level=log_lvl
        )

    def initialize_app(self, argv):
        self.client = client.Client(
            config_file=self.options.config_file,
            zookeeper_url=self.options.mesos_url,
            mesos_url=self.options.mesos_url,
            marathon_url=self.options.marathon_url,
            chronos_url=self.options.chronos_url)


def main(argv=sys.argv[1:]):
    return KollaMesosShell().run(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
