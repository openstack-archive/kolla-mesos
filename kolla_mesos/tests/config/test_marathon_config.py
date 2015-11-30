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

from kolla_mesos.tests import base
from kolla_mesos.tests.fakes import config_file as fake_config_file


CONF = cfg.CONF
CONF.import_group('marathon', 'kolla_mesos.config.marathon')


MARATHON_TEXT_CONFIG = """
[marathon]
host = test.local:8080
timeout = 30
"""


class TestMarathonConfig(base.BaseTestCase):

    def test_cli_config(self):
        argv = ['--marathon-host', 'test.local:8080', '--marathon-timeout',
                '30']
        CONF(argv, project='kolla-mesos')
        self.assertEqual(CONF.marathon.host, 'test.local:8080')
        self.assertEqual(CONF.marathon.timeout, 30)

    @fake_config_file.FakeConfigFile(MARATHON_TEXT_CONFIG)
    def test_file_config(self):
        CONF([], project='kolla-mesos', default_config_files=['/dev/null'])
        self.assertEqual(CONF.marathon.host, 'test.local:8080')
        self.assertEqual(CONF.marathon.timeout, 30)
