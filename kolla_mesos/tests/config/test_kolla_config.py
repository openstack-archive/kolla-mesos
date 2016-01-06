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
CONF.import_group('kolla', 'kolla_mesos.config.kolla')


KOLLA_TEXT_CONFIG = """
[kolla]
namespace = test_namespace
tag = test_tag
base = test_base
base_tag = test_base_tag
install_type = test_install_type
profile = test_profile
"""


class TestKollaConfig(base.BaseTestCase):

    def _asserts(self):
        self.assertEqual('test_namespace', CONF.kolla.namespace)
        self.assertEqual('test_tag', CONF.kolla.tag)
        self.assertEqual('test_base', CONF.kolla.base)
        self.assertEqual('test_base_tag', CONF.kolla.base_tag)
        self.assertEqual('test_install_type', CONF.kolla.install_type)
        self.assertEqual('test_profile', CONF.kolla.profile)

    def test_cli_config(self):
        argv = ['--kolla-namespace', 'test_namespace', '--kolla-tag',
                'test_tag', '--kolla-base', 'test_base', '--kolla-base-tag',
                'test_base_tag', '--kolla-install-type', 'test_install_type',
                '--kolla-profile', 'test_profile']
        CONF(argv, project='kolla-mesos')
        self._asserts()

    @fake_config_file.FakeConfigFile(KOLLA_TEXT_CONFIG)
    def test_file_config(self):
        CONF([], project='kolla-mesos', default_config_files=['/dev/null'])
        self._asserts()
