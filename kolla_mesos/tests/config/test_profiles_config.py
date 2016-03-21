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
CONF.import_group('profiles', 'kolla_mesos.config.profiles')


PROFILES_TEXT_CONFIG = """
[profiles]
infra = test1, test2
main = test1
default = test1, test2, test3, test4, test5
gate = test1, test2, test3, test4
"""


class TestProfilesConfig(base.BaseTestCase):

    def _asserts(self):
        self.assertEqual(['test1', 'test2'], CONF.profiles.infra)
        self.assertEqual(['test1'], CONF.profiles.main)
        self.assertEqual(['test1', 'test2', 'test3', 'test4',
                         'test5'], CONF.profiles.default)
        self.assertEqual(['test1', 'test2', 'test3',
                         'test4'], CONF.profiles.gate)

    def test_cli_config(self):
        argv = ['--profiles-infra', 'test1,test2',
                '--profiles-main', 'test1', '--profiles-default',
                'test1,test2,test3,test4,test5', '--profiles-gate',
                'test1,test2,test3,test4']
        CONF(argv, project='kolla-mesos')
        self._asserts()

    @fake_config_file.FakeConfigFile(PROFILES_TEXT_CONFIG)
    def test_file_config(self):
        CONF([], project='kolla-mesos', default_config_files=['/dev/null'])
        self._asserts()
