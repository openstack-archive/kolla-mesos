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
import requests_mock

from kolla_mesos import mesos
from kolla_mesos.tests import base


CONF = cfg.CONF

EXAMPLE_STATE = {
    'frameworks': [{
        'tasks': [{
            'name': 'neutron-server',
            'state': 'TASK_RUNNING'
        }]
    }, {
        'tasks': [{
            'name': 'ChronosTask:neutron-ansible-tasks',
            'state': 'TASK_FINISHED'
        }]
    }]
}


class TestClient(base.BaseTestCase):

    def setUp(self):
        super(TestClient, self).setUp()
        self.client = mesos.Client()
        CONF.set_override('host', 'http://localhost:5050', group='mesos')
        CONF.set_override('timeout', 5, group='mesos')

    def test_create_url(self):
        url = self.client._create_url('test')
        self.assertEqual('http://localhost:5050/test', url)

    @requests_mock.mock()
    def test_get_state(self, req_mock):
        req_mock.get('http://localhost:5050/state.json', json=EXAMPLE_STATE)
        state = self.client.get_state()
        self.assertDictEqual(EXAMPLE_STATE, state)

    @requests_mock.mock()
    def test_get_frameworks(self, req_mock):
        req_mock.get('http://localhost:5050/state.json', json=EXAMPLE_STATE)
        frameworks = self.client.get_frameworks()
        self.assertListEqual([{
            'tasks': [{
                'name': 'neutron-server',
                'state': 'TASK_RUNNING'
            }]
        }, {
            'tasks': [{
                'name': 'ChronosTask:neutron-ansible-tasks',
                'state': 'TASK_FINISHED'
            }]
        }], frameworks)

    @requests_mock.mock()
    def test_get_tasks(self, req_mock):
        req_mock.get('http://localhost:5050/state.json', json=EXAMPLE_STATE)
        tasks = self.client.get_tasks()
        self.assertListEqual([{
            'name': 'neutron-server',
            'state': 'TASK_RUNNING'
        }, {
            'name': 'ChronosTask:neutron-ansible-tasks',
            'state': 'TASK_FINISHED'
        }], tasks)
