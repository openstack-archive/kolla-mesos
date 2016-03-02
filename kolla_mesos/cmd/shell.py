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

from kolla_mesos.cli import utils
from kolla_mesos.common import file_utils

VERSION = '1.0'
CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')


class KollaMesosShell(app.App):
    def __init__(self):
        super(KollaMesosShell, self).__init__(
            description='Kolla-mesos command-line interface',
            version=VERSION,
            command_manager=commandmanager.CommandManager('kolla_mesos.cli'),
            deferred_help=True,
            )

    def build_option_parser(self, description, version,
                            argparse_kwargs=None):
        parser = super(KollaMesosShell, self).build_option_parser(
            description, version, argparse_kwargs)

        parser.add_argument(
            '--config-file',
            action='store',
            default=utils.env('KM_CONFIG_FILE',
                              default='/etc/kolla-mesos/kolla-mesos.conf'),
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
        service_dir = os.path.join(file_utils.find_base_dir(), 'services')

        parser.add_argument(
            '--service-dir',
            action='store',
            default=utils.env('KM_SERVICE_DIR', default=service_dir),
            help='Directory with services, (Env: KM_SERVICE_DIR)'
        )

        return parser

    def initialize_app(self, argv):
        default_configs = [self.options.config_file]
        CONF([], project='kolla-mesos', default_config_files=default_configs)

        if self.options.mesos_url:
            CONF.mesos.host = self.options.mesos_url
        if self.options.chronos_url:
            CONF.chronos.host = self.options.chronos_url
        if self.options.zookeeper_url:
            CONF.zookeeper.host = self.options.zookeeper_url
        if self.options.marathon_url:
            CONF.marathon.host = self.options.marathon_url
        if self.options.verbose_level > 1:
            CONF.log_opt_values(logging.getLogger('kolla-mesos'),
                                logging.DEBUG)


def main(argv=sys.argv[1:]):
    return KollaMesosShell().run(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
