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

import json
import os.path

import mock
from oslo_config import cfg
from zake import fake_client

from kolla_mesos import service
from kolla_mesos.tests import base


class TestRun(base.BaseTestCase):

    def setUp(self):
        super(TestRun, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')

    def test_run(self):
        # TODO(asalkeld)
        pass


class TestKill(base.BaseTestCase):

    def setUp(self):
        super(TestKill, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        cfg.CONF.set_override('deployment_id', 'did', group='kolla')

    @mock.patch.object(service.MarathonApp, 'kill')
    def test_kill(self, m_kill):
        self.client.create('/kolla/did/openstack/nova/nova-api',
                           json.dumps({'name': 'openstack/nova/nova-api'}),
                           makepath=True)

        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.kill_service('openstack/nova/nova-api')
            m_kill.assert_called_once_with(self.client)


class TestGet(base.BaseTestCase):

    def setUp(self):
        super(TestGet, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')

    @mock.patch.object(service.ChronosTask, 'get_state')
    @mock.patch.object(service.MarathonApp, 'get_state')
    def test_marathon(self, m_get_state, c_get_state):
        service.get_service('openstack/nova/nova-api')
        self.assertEqual([], c_get_state.mock_calls)
        m_get_state.assert_called_once_with('openstack/nova/nova-api', None)

    @mock.patch.object(service.ChronosTask, 'get_state')
    @mock.patch.object(service.MarathonApp, 'get_state')
    def test_chronos(self, m_get_state, c_get_state):
        service.get_service('openstack-nova-nova-init')
        self.assertEqual([], m_get_state.mock_calls)
        c_get_state.assert_called_once_with('openstack-nova-nova-init', None)


class TestList(base.BaseTestCase):

    def setUp(self):
        super(TestList, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')

    def test_list(self):
        # TODO(asalkeld)
        pass
