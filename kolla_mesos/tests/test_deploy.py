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
import yaml

from kolla_mesos.cmd import deploy
from kolla_mesos.tests import base


CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('mesos', 'kolla_mesos.config.mesos')

YAML_SERVICES_CONFIG = """
name: openstack/cinder/cinder-api
container:
  image: "cinder-api:a.b.c"
service:
  daemon:
    dependencies: [cinder-tasks/create_user,
                   keystone-tasks/running,
                   rabbitmq/daemon]
    command: /usr/bin/cinder-api
    files:
      cinder.conf.j2:
        source: ["config/cinder/templates/cinder.conf.j2",
                 "/etc/kolla-mesos/config/cinder/cinder-api.conf"]
        dest: /etc/cinder/cinder.conf
        owner: cinder
        perm: "0600"
"""


class TestClient(base.BaseTestCase):

    @requests_mock.mock()
    def setUp(self, req_mock):
        super(TestClient, self).setUp()
        CONF.set_override('host', 'http://localhost:4400', group='chronos')
        CONF.set_override('timeout', 5, group='chronos')
        CONF.set_override('host', 'http://127.0.0.1:8080', group='marathon')
        CONF.set_override('host', 'http://127.0.0.1:5050', group='mesos')
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
        CONF.set_override('deployment_id', 'test', group='kolla')
        self.worker.gen_deployment_id()
        self.assertEqual('test', self.worker.deployment_id)

    @mock.patch('kolla_mesos.cmd.deploy.sys')
    def test_gen_deployment_id_without_parameters(self, mock_sys):
        CONF.set_override('deployment_id', None, group='kolla')
        self.worker.gen_deployment_id()
        mock_sys.exit.assert_called_once_with(1)

    @mock.patch('kolla_mesos.cmd.deploy.yaml')
    @mock.patch('kolla_mesos.cmd.deploy.zk_utils')
    @mock.patch.object(deploy.KollaWorker,
                       '_write_common_config_to_zookeeper')
    def test_write_to_zookeeper(self, mock_common, mock_utils, mock_yaml):
        CONF.set_override('force', True)

        self.worker.get_jinja_vars = mock.MagicMock(
            return_value={'image': 'test1',
                          'test2': '',
                          'controller_nodes': '1',
                          'compute_nodes': '1'})
        mock_yaml.load = mock.MagicMock(
            return_value=yaml.load(YAML_SERVICES_CONFIG))
        mock_common.return_value = ''

        self.worker.setup_working_dir()
        self.worker.gen_deployment_id()
        self.worker.write_to_zookeeper()

        self.assertTrue(len(mock_utils.mock_calls) > 1)
        expected_calls = ['set', 'delete', 'ensure_path', 'exists']
        for call in mock_utils.mock_calls:
            methods = str(call).split('.')
            if len(methods) > 3:
                function_name = methods[3].split('(')[0]
                self.assertIn(function_name, expected_calls)

    @mock.patch('kolla_mesos.cmd.deploy.json')
    @mock.patch('kolla_mesos.cmd.deploy.open')
    @mock.patch('kolla_mesos.cmd.deploy.os')
    def test_start(self, mock_os, mock_open, mock_json):
        self.worker._start_chronos_job = mock.MagicMock()
        self.worker._start_marathon_app = mock.MagicMock()
        mock_os.path = mock.MagicMock()
        mock_os.walk = mock.MagicMock(
            return_value=[('/', ('tmp1', 'tmp2'), ('file1', )),
                          ('/', ('mdir', ), ('marathon', 'marathon2'))])

        self.worker.setup_working_dir()
        self.worker.gen_deployment_id()
        self.worker.start()

        self.assertEqual(1, self.worker._start_chronos_job.call_count)
        self.assertEqual(2, self.worker._start_marathon_app.call_count)
