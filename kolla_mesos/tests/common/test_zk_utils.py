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

import mock
from zake import fake_client

from kolla_mesos.common import zk_utils
from kolla_mesos.tests import base


class TestConfig(base.BaseTestCase):

    def setUp(self):
        super(TestConfig, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)

    def test_list_all(self):
        self.client.create('/kolla/t1/status/q/x',
                           'val-1', makepath=True)
        self.client.create('/kolla/t1/variables/x',
                           'val-2', makepath=True)

        with mock.patch.object(zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            res = zk_utils.list_all('/')
            self.assertEqual({'/kolla/t1/status/q/x': 'val-1',
                              '/kolla/t1/variables/x': 'val-2'}, res)

    def test_get_one(self):
        self.client.create('/kolla/t1/variables/x',
                           'val', makepath=True)

        with mock.patch.object(zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            res = zk_utils.get_one('/kolla/t1/variables/x')
            self.assertEqual({'/kolla/t1/variables/x': 'val'}, res)

    def test_set_one(self):
        self.client.create('/kolla/t1/variables/x',
                           'old', makepath=True)

        with mock.patch.object(zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            zk_utils.set_one('/kolla/t1/variables/x', 'new')
            val, _st = self.client.get('/kolla/t1/variables/x')
            self.assertEqual('new', val)
