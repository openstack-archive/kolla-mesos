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
CONF.import_group('network', 'kolla_mesos.config.network')


NETWORK_TEXT_CONFIG = """
[network]
private_interface = test_priv_iface
public_interface = test_pub_iface
"""


class TestNetworkConfig(base.BaseTestCase):

    def _asserts(self):
        self.assertEqual(CONF.network.private_interface, 'test_priv_iface')
        self.assertEqual(CONF.network.public_interface, 'test_pub_iface')

    def test_cli_config(self):
        argv = ['--network-private-interface', 'test_priv_iface',
                '--network-public-interface', 'test_pub_iface']
        CONF(argv, project='kolla-mesos')
        self._asserts()

    @fake_config_file.FakeConfigFile(NETWORK_TEXT_CONFIG)
    def test_file_config(self):
        CONF([], project='kolla-mesos', default_config_files=['/dev/null'])
        self._asserts()
