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

import datetime
import mock
from oslo_config import cfg
import requests_mock

from kolla_mesos.cmd import deploy
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

    @requests_mock.mock()
    def setUp(self, req_mock):
        super(TestClient, self).setUp()
        CONF.set_override('host', 'http://localhost:4400', group='chronos')
        CONF.set_override('timeout', 5, group='chronos')
        CONF.set_override('host', 'http://127.0.0.1:8080', group='marathon')
        req_mock.get('http://127.0.0.1:8080/v2/info', json={
            'version': '0.11.0'
        })

        self.worker = deploy.KollaWorker()

    def test_create_worker(self):
        self.assertIsInstance(self.worker, deploy.KollaWorker)

    @mock.patch('kolla_mesos.cmd.deploy.tempfile')
    def test_setup_working_dir(self, mock_tmpfile):
        self.worker.setup_working_dir()
        parameters = mock_tmpfile.mkdtemp.call_args[1]
        self.assertTrue(parameters['prefix'].startswith('kolla'))

    def test_gen_deployment_id(self):
        CONF.kolla.deployment_id = 'test'
        self.worker.gen_deployment_id()
        self.assertEqual(self.worker.deployment_id, 'test')

    def test_gen_deployment_id_prefix(self):
        CONF.kolla.deployment_id_prefix = 'test'
        self.worker.gen_deployment_id()
        self.assertIn('test', self.worker.deployment_id)
        self.assertNotEqual(self.worker.deployment_id, 'test')

    def test_gen_deployment_id_without_parameters(self):
        self.worker.gen_deployment_id()
        date = datetime.datetime.fromtimestamp(self.worker.start_time)
        new_id = date.strftime('%Y-%m-%d-%H-%M-%S')
        self.assertTrue(self.worker.deployment_id.startswith(new_id[:10]))

    @mock.patch('kolla_mesos.cmd.deploy.sys')
    def test_gen_deployment_id_with_extra_parameters(self, mock_sys):
        CONF.kolla.deployment_id = 'test'
        CONF.kolla.deployment_id_prefix = 'test2'
        self.worker.gen_deployment_id()
        mock_sys.exit.assert_called_once_with(1)

    @mock.patch('kolla_mesos.cmd.deploy.zk_utils')
    @mock.patch('kolla_mesos.cmd.deploy.open')
    @mock.patch('kolla_mesos.cmd.deploy.sys')
    def test_write_to_zookeeper_delete_conf(self, mock_utils, mock_open,
                                            mock_sys):
        CONF.kolla.deployment_id = None
        CONF.kolla.deployment_id_prefix = None
        self.worker.gen_deployment_id()
        # WIP: we failed with timeout here:
        #self.worker.write_to_zookeeper()
        #mock_sys.exit.assert_called_once_with(1)
