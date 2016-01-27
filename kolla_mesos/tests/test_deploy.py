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
import yaml

from kolla_mesos.cmd import deploy
from kolla_mesos.tests import base


CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')

YAML_SERVICES_CONFIG = """
config:
  source: "test1.yml"
  keystone:
    keystone-api:
      keystone-api.conf:
        source: ["config/keystone/templates/keystone-api.conf.j2",
                 "/etc/kolla/config/keystone.conf"]
        dest: /etc/keystone/keystone-api.conf
        owner: glance
        perm: "0600"
  rabbitmq:
    rabbitmq-server:
      rabbitmq-server.conf:
        source: ["config/rabbitmq/templates/rabbitmq-server.conf.j2",
                 "/etc/kolla/config/rabbitmq-server.conf"]
        dest: /etc/rabbitmq/rabbitmq-server.conf
  mariadb:
    mariadb-server:
      mariadb-server.conf:
        source: ["config/mariadb/templates/mariadb-server.conf.j2",
                 "/etc/kolla/config/mariadb-server.conf"]
        dest: /etc/mariadb/mariadb-server.conf
  glance:
    glance-api:
      glance-api.conf:
        source: "/config/glance/templates/glance-api.conf.j2"
        dest: /etc/glance/glance-api.conf
    glance-registry:
      glance-registry.conf:
        source: "config/glance/templates/glance-registry.conf.j2"
        dest: /etc/glance/glance-registry.conf
  horizon:
    horizon:
      openstack-horizon.conf:
        source: "/config/horizon/templates/openstack-dashboard.conf.j2"
        dest: /etc/horizon/openstack-dashboard.conf
commands:
  source: "/etc/test2.yaml"
  glance:
    glance-api:
      db_sync:
        run_once: True
        command: kolla_extend_start
      glance_api:
        daemon: True
        command: /usr/bin/glance-api
        requires: [/kolla/1/variables/glance_database/.done,
                   /kolla/1/variables/glance_database_user_create/.done]
        register: /kolla/1/variables/glance_setup/.done
    glance-registry:
      glance-registry:
        daemon: True
        command: /usr/bin/glance-registry
  keystone:
    keystone-api:
      keystone-api:
        daemon: True
        command: /usr/bin/keystone-api
  mariadb:
    mariadb-server:
      mariadb-server:
        daemon: True
        command: service mariadb-server start
  rabbitmq:
    rabbitmq-server:
      rabbitmq-server:
        daemon: True
        command: service rabbitmq-server start
  horizon:
    horizon:
      apache:
        daemon: False
        command: service apache2 start
"""


class TestClient(base.BaseTestCase):

    @requests_mock.mock()
    def setUp(self, req_mock):
        super(TestClient, self).setUp()
        CONF.set_override('host', 'http://localhost:4400', group='chronos')
        CONF.set_override('timeout', 5, group='chronos')
        CONF.set_override('host', 'http://127.0.0.1:8080', group='marathon')
        CONF.set_override('deployment_id', None, group='kolla')
        CONF.set_override('deployment_id_prefix', None, group='kolla')
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
        self.assertEqual(self.worker.deployment_id, 'test')

    def test_gen_deployment_id_prefix(self):
        CONF.set_override('deployment_id_prefix', 'test', group='kolla')
        self.worker.gen_deployment_id()
        self.assertIn('test', self.worker.deployment_id)
        self.assertNotEqual(self.worker.deployment_id, 'test')

    def test_gen_deployment_id_without_parameters(self):
        self.worker.gen_deployment_id()
        self.assertTrue(self.worker.deployment_id, 'openstack')

    @mock.patch('kolla_mesos.cmd.deploy.sys')
    def test_gen_deployment_id_with_extra_parameters(self, mock_sys):
        CONF.set_override('deployment_id', 'test', group='kolla')
        CONF.set_override('deployment_id_prefix', 'test2', group='kolla')
        self.worker.gen_deployment_id()
        mock_sys.exit.assert_called_once_with(1)

    @mock.patch('kolla_mesos.cmd.deploy.open')
    @mock.patch('kolla_mesos.cmd.deploy.file_utils')
    @mock.patch('kolla_mesos.cmd.deploy.yaml')
    @mock.patch('kolla_mesos.cmd.deploy.json')
    @mock.patch('kolla_mesos.cmd.deploy.zk_utils')
    def test_write_to_zookeeper(self, mock_utils, mock_json, mock_yaml,
                                mock_file_utils, mock_open):
        CONF.set_override('force', True)

        self.worker.get_jinja_vars = mock.MagicMock(
            return_value={'image': 'test1', 'test2': ''})
        mock_yaml.load = mock.MagicMock(
            return_value=yaml.load(YAML_SERVICES_CONFIG))
        mock_file_utils = mock.MagicMock()
        mock_file_utils.find_file = mock.MagicMock(spec=file)
        mock_open.return_value = mock.MagicMock(spec=file)

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

    @mock.patch('kolla_mesos.cmd.deploy.open')
    def test_write_openrc(self, mock_open):
        mock_open.return_value = mock.MagicMock(spec=file)
        file_handle = mock_open.return_value.__enter__.return_value

        self.worker.write_openrc()

        mock_open.assert_called_once_with('openrc', 'w')
        self.assertEqual(file_handle.write.call_count, 1)

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

        self.assertEqual(self.worker._start_chronos_job.call_count, 1)
        self.assertEqual(self.worker._start_marathon_app.call_count, 2)

    @mock.patch('kolla_mesos.cmd.deploy.jinja_utils')
    @mock.patch('kolla_mesos.cmd.deploy.yaml')
    @mock.patch('kolla_mesos.cmd.deploy.open')
    def test_get_jinja_vars(self, mock_open, mock_yaml, mock_jutils):
        CONF.set_override('deployment_id', 'test', group='kolla')
        mock_yaml.load = mock.MagicMock(return_value={})
        self.worker.setup_working_dir()
        self.worker.gen_deployment_id()
        result = self.worker.get_jinja_vars()

        self.assertIsInstance(result, dict)
        self.assertEqual(result['deployment_id'], 'test')
        self.assertEqual(result['node_config_directory'], '')
