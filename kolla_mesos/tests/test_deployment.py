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
import six
from zake import fake_client

from kolla_mesos import configuration
from kolla_mesos import deployment
from kolla_mesos import exception
from kolla_mesos.tests import base


class TestWriteOpenRC(base.BaseTestCase):

    def setUp(self):
        super(TestWriteOpenRC, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)

    def test_write_openrc_ok(self):
        variables = {'keystone_admin_password': 'foofee',
                     'kolla_internal_address': 'here.not',
                     'keystone_admin_port': '4511',
                     'openstack_region_name': 'there',
                     'keystone_auth_host': 'not.here'}

        configuration.write_variables_zookeeper(self.client, variables)

        m_open = mock.mock_open()
        with mock.patch('kolla_mesos.deployment.open', m_open):
            file_handle = m_open.return_value.__enter__.return_value

            with mock.patch.object(deployment.zk_utils,
                                   'connection') as m_zk_c:
                m_zk_c.return_value.__enter__.return_value = self.client
                deployment.write_openrc('openrc')

                m_open.assert_called_once_with('openrc', 'w')
                self.assertEqual(1, file_handle.write.call_count)

    def test_write_openrc_fail(self):
        # missing variable "keystone_admin_port"
        variables = {'keystone_admin_password': 'foofee',
                     'kolla_internal_address': 'here.not',
                     'openstack_region_name': 'there',
                     'keystone_auth_host': 'not.here'}

        configuration.write_variables_zookeeper(self.client, variables)
        with mock.patch.object(deployment.zk_utils, 'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            exc = self.assertRaises(exception.KollaNotFoundException,
                                    deployment.write_openrc, 'openrc')
            self.assertIn('keystone_admin_port', six.text_type(exc))
