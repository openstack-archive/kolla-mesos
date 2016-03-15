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


class TestAPI(base.BaseTestCase):

    def setUp(self):
        super(TestAPI, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        cfg.CONF.set_override('deployment_id', 'did', group='kolla')

    @mock.patch.object(service.config, 'apply_deployment_vars')
    @mock.patch.object(service.MarathonApp, 'run')
    def test_run_marathon(self, m_run, m_apply):
        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.run_service('openstack/keystone/keystone-api',
                                self.service_dir)
            m_run.assert_called_once_with()

        # assert that we have the basics in zk
        exp_nodes = ['/kolla/common/kolla_mesos_start.py',
                     '/kolla/did/variables/keystone_admin_port',
                     '/kolla/did/openstack/keystone/keystone-api']
        for node in exp_nodes:
            self.assertTrue(self.client.exists(node), node)

    @mock.patch.object(service.config, 'apply_deployment_vars')
    @mock.patch.object(service.ChronosTask, 'run')
    def test_run_chronos(self, m_run, m_apply):
        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.run_service('openstack/keystone/keystone-init',
                                self.service_dir)
            m_run.assert_called_once_with()

        # assert that we have the basics in zk
        exp_nodes = ['/kolla/common/kolla_mesos_start.py',
                     '/kolla/did/variables/keystone_admin_port',
                     '/kolla/did/openstack/keystone/keystone_ansible_tasks']
        for node in exp_nodes:
            self.assertTrue(self.client.exists(node), node)

    @mock.patch.object(service.MarathonApp, 'kill')
    def test_kill(self, m_kill):
        self.client.create('/kolla/did/openstack/nova/nova-api',
                           json.dumps({'name': 'openstack/nova/nova-api',
                                       'service': {}}),
                           makepath=True)

        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.kill_service('openstack/nova/nova-api')
            m_kill.assert_called_once_with(self.client)

    @mock.patch.object(service.ChronosTask, 'get_state')
    @mock.patch.object(service.MarathonApp, 'get_state')
    def test_get_marathon(self, m_get_state, c_get_state):
        self.client.create('/kolla/did/openstack/nova/nova-api',
                           json.dumps({'name': 'openstack/nova/nova-api',
                                       'service': {}}),
                           makepath=True)
        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.get_service('openstack/nova/nova-api')
            self.assertEqual([], c_get_state.mock_calls)
            m_get_state.assert_called_once_with(None)

    @mock.patch.object(service.ChronosTask, 'get_state')
    @mock.patch.object(service.MarathonApp, 'get_state')
    def test_get_chronos(self, m_get_state, c_get_state):
        self.client.create('/kolla/did/openstack/nova/nova_init',
                           json.dumps({'name': 'openstack/nova/nova_init',
                                       'task': {}}),
                           makepath=True)
        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.get_service('openstack-nova-nova_init')
            self.assertEqual([], m_get_state.mock_calls)
            c_get_state.assert_called_once_with(None)

    @mock.patch.object(service.MarathonApp, 'scale')
    def test_scale_marathon(self, m_scale):
        self.client.create('/kolla/did/openstack/nova/nova-api',
                           json.dumps({'name': 'openstack/nova/nova-api',
                                       'service': {}}),
                           makepath=True)
        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.scale_service('openstack/nova/nova-api', 2, force=False)
            m_scale.assert_called_once_with(2, False)

    @mock.patch.object(service.config, 'apply_deployment_vars')
    @mock.patch.object(service.MarathonApp, 'update')
    def test_update_marathon(self, m_update, m_apply):
        self.client.create('/kolla/did/openstack/nova/nova-api',
                           json.dumps({'name': 'openstack/nova/nova-api',
                                       'service': {}}),
                           makepath=True)
        with mock.patch.object(service.zk_utils,
                               'connection') as m_zk_c:
            m_zk_c.return_value.__enter__.return_value = self.client
            service.update_service('openstack/nova/nova-api', self.service_dir)
            m_update.assert_called_once_with()

    @mock.patch.object(service.ChronosTask, 'list_all')
    @mock.patch.object(service.MarathonApp, 'list_all')
    def test_list(self, m_list, c_list):
        service.list_services()
        c_list.assert_called_once_with()
        m_list.assert_called_once_with()
