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
from oslo_config import cfg
from zake import fake_client

from kolla_mesos.cmd import show_tasks
from kolla_mesos.tests import base
from kolla_mesos.tests.fakes import mesos as fake_mesos


CONF = cfg.CONF
CONF.import_group('mesos', 'kolla_mesos.config.mesos')


class ShowTasksTest(base.BaseTestCase):

    def setUp(self):
        super(ShowTasksTest, self).setUp()
        CONF.set_override('host', 'http://127.0.0.1:5050', group='mesos')
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        self.dep_id = 'test'

    @fake_mesos.FakeMesosStateSlaves()
    def test_get_tasks_sanity(self):
        var = '/kolla/test/status'
        exp = {'register': '%s/cinder-api/db_sync' % var,
               'requires': [
                   '%s/cinder_ansible_tasks/create_database' % var,
                   '%s/cinder_ansible_tasks/database_user_create' % var]}

        tasks = show_tasks.get_tasks(self.dep_id)
        self.assertEqual(exp, tasks['cinder-api/db_sync'])

    @fake_mesos.FakeMesosStateSlaves()
    @mock.patch.object(show_tasks.zk_utils, 'connection')
    def test_get_status_waiting(self, m_zk_c):
        m_zk_c.return_value.__enter__.return_value = self.client
        tasks = show_tasks.get_tasks(self.dep_id)
        # just get what we want for the test
        test_tasks = {'cinder-api/db_sync':
                      tasks['cinder-api/db_sync']}
        var = '/kolla/test/status'
        exp = {
            'register': ('%s/cinder-api/db_sync' % var, 'waiting'),
            'requirements': {
                '%s/cinder_ansible_tasks/create_database' % var: 'running',
                '%s/cinder_ansible_tasks/database_user_create' % var: 'done'}
        }
        self.client.create(
            '%s/cinder-api/db_sync' % var,
            'waiting', makepath=True)
        self.client.create(
            '%s/cinder_ansible_tasks/create_database' % var,
            'running', makepath=True)
        self.client.create(
            '%s/cinder_ansible_tasks/database_user_create' % var,
            'done', makepath=True)
        status = show_tasks.get_status(test_tasks)
        self.assertEqual({'cinder-api/db_sync': exp}, status)

    @fake_mesos.FakeMesosStateSlaves()
    @mock.patch.object(show_tasks.zk_utils, 'connection')
    def test_get_status_deps_done(self, m_zk_c):
        m_zk_c.return_value.__enter__.return_value = self.client
        tasks = show_tasks.get_tasks(self.dep_id)
        # just get what we want for the test
        test_tasks = {'cinder-api/db_sync':
                      tasks['cinder-api/db_sync']}
        var = '/kolla/test/status'
        at = '%s/cinder_ansible_tasks' % var
        exp = {
            'register': ('%s/cinder-api/db_sync' % var, ''),
            'requirements': {
                '%s/create_database' % at: 'done',
                '%s/database_user_create' % at: 'done'}}

        # create the done states
        self.client.create(
            '%s/cinder_ansible_tasks/create_database' % var,
            'done', makepath=True)
        self.client.create(
            '%s/cinder_ansible_tasks/database_user_create' % var,
            'done', makepath=True)

        status = show_tasks.get_status(test_tasks)
        self.assertEqual({'cinder-api/db_sync': exp}, status)

    @fake_mesos.FakeMesosStateSlaves()
    @mock.patch.object(show_tasks.zk_utils, 'connection')
    def test_get_status_done(self, m_zk_c):
        m_zk_c.return_value.__enter__.return_value = self.client
        tasks = show_tasks.get_tasks(self.dep_id)
        # just get what we want for the test
        test_tasks = {'cinder-api/db_sync':
                      tasks['cinder-api/db_sync']}
        var = '/kolla/test/status'
        at = '%s/cinder_ansible_tasks' % var
        exp = {
            'register': ('%s/cinder-api/db_sync' % var, 'done'),
            'requirements': {
                '%s/create_database' % at: 'done',
                '%s/database_user_create' % at: 'done'}}

        # create the done state
        self.client.create(
            '%s/cinder_ansible_tasks/create_database' % var,
            'done', makepath=True)
        self.client.create(
            '%s/cinder_ansible_tasks/database_user_create' % var,
            'done', makepath=True)
        self.client.create('%s/cinder-api/db_sync' % var, 'done',
                           makepath=True)

        status = show_tasks.get_status(test_tasks)
        self.assertEqual({'cinder-api/db_sync': exp}, status)
