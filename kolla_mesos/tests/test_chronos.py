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
import requests_mock

from kolla_mesos import chronos
from kolla_mesos import exception
from kolla_mesos.tests import base


CONF = cfg.CONF

EXAMPLE_CHRONOS_JOB = {
    "name": "/keystone-bootstrap",
    "mem": 32.0,
    "cpus": 0.3,
    "container": {
        "type": "DOCKER",
        "image": "/--kolla_ansible:",
        "network": "HOST"
    },
    "environmentVariables": [
        {"name": "KOLLA_CONFIG_STRATEGY", "value": "COPY_ONCE"},
        {"name": "KOLLA_CONFIG", "value": {
            "command": "/usr/local/bin/kolla_mesos_start",
            "config_files": [{
                "source": ("zk://localhost:2181/kolla/config/mariadb/mariadb/"
                           "kolla_mesos_start.py"),
                "dest": "/usr/local/bin/kolla_mesos_start",
                "owner": "root",
                "perm": "0755"
            }]
        }},
        {"name": "KOLLA_GROUP", "value": "keystone"},
        {"name": "KOLLA_ROLE", "value": "keystone_bootstrap"},
        {"name": "KOLLA_ZK_HOSTS", "value": "localhost:2181"}
    ]
}


class TestClient(base.BaseTestCase):

    def setUp(self):
        super(TestClient, self).setUp()
        self.client = chronos.Client()
        CONF.set_override('host', 'http://localhost:4400', group='chronos')
        CONF.set_override('timeout', 5, group='chronos')

    def test_create_client(self):
        self.assertIsInstance(self.client, chronos.Client)

    def test_create_url(self):
        url = self.client._create_url('test')
        self.assertEqual(url, 'http://localhost:4400/test')

    @requests_mock.mock()
    def test_add_job(self, req_mock):
        req_mock.get('http://localhost:4400/scheduler/jobs', json=[])
        req_mock.post('http://localhost:4400/scheduler/iso8601')
        self.client.add_job(EXAMPLE_CHRONOS_JOB)

    @mock.patch.object(chronos, 'LOG')
    @requests_mock.mock()
    def test_add_job_already_existing(self, log_mock, req_mock):
        req_mock.get('http://localhost:4400/scheduler/jobs', json=[{
            'name': '/keystone-bootstrap'
        }])
        req_mock.post('http://localhost:4400/scheduler/iso8601')
        self.client.add_job(EXAMPLE_CHRONOS_JOB)
        log_mock.info.assert_called_with('Job %s is already added. If you '
                                         'want to replace it, please use '
                                         '--force flag',
                                         '/keystone-bootstrap')

    @requests_mock.mock()
    def test_add_job_already_existing_force(self, req_mock):
        CONF.set_override('force', True)
        req_mock.get('http://localhost:4400/scheduler/jobs', json=[{
            'name': '/keystone-bootstrap'
        }])
        req_mock.post('http://localhost:4400/scheduler/iso8601')
        self.assertRaises(exception.ChronosRollback, self.client.add_job,
                          EXAMPLE_CHRONOS_JOB)

    @requests_mock.mock()
    def test_get_jobs(self, req_mock):
        req_mock.get('http://localhost:4400/scheduler/jobs',
                     json=[EXAMPLE_CHRONOS_JOB])
        response = self.client.get_jobs()

        self.assertIsInstance(response, list)

        job = response[0]

        self.assertIsInstance(job, dict)
        self.assertDictEqual(job, EXAMPLE_CHRONOS_JOB)
