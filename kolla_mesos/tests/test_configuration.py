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

from kolla_mesos import configuration
from kolla_mesos import exception
from kolla_mesos.tests import base
from kolla_mesos.tests.fakes import mesos as fake_mesos

CONF = cfg.CONF


class TestConfiguration(base.BaseTestCase):

    def setUp(self):
        super(TestConfiguration, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)

    @fake_mesos.FakeMesosStateTaggedSlaves()
    def test_get_jinja_vars_multinode_autodetect_resources(self):
        CONF.set_override('deployment_id', 'test', group='kolla')
        result = {
            'multinode': 'yes',
            'autodetect_resources': 'yes'}
        configuration.apply_deployment_vars(result)

        self.assertEqual('3', result['controller_nodes'])
        self.assertEqual('2', result['compute_nodes'])
        self.assertEqual('2', result['storage_nodes'])
        self.assertEqual('7', result['all_nodes'])

    def test_get_jinja_vars_multinode_no_autodetect_resources(self):
        CONF.set_override('deployment_id', 'test', group='kolla')
        result = {
            'multinode': 'yes',
            'autodetect_resources': 'no',
            'controller_nodes': 3,
            'compute_nodes': 2,
            'storage_nodes': 2}
        configuration.apply_deployment_vars(result)

        self.assertEqual('3', result['controller_nodes'])
        self.assertEqual('2', result['compute_nodes'])
        self.assertEqual('2', result['storage_nodes'])
        self.assertEqual('7', result['all_nodes'])

    def test_get_jinja_vars_aio(self):
        CONF.set_override('deployment_id', 'test', group='kolla')
        result = {'multinode': 'no'}
        configuration.apply_deployment_vars(result)

        self.assertEqual('1', result['controller_nodes'])
        self.assertEqual('1', result['storage_nodes'])
        self.assertEqual('1', result['all_nodes'])
        self.assertEqual('', result['controller_constraints'])
        self.assertEqual('', result['compute_constraints'])
        self.assertEqual('', result['controller_compute_constraints'])
        self.assertEqual('', result['storage_constraints'])

    def test_get_jinja_vars_hostname_aio(self):
        CONF.set_override('deployment_id', 'test', group='kolla')
        result = {
            'multinode': 'no',
            'mesos_aio_hostname': 'test-slave'}
        configuration.apply_deployment_vars(result)

        self.assertEqual('1', result['controller_nodes'])
        self.assertEqual('1', result['storage_nodes'])
        self.assertEqual('1', result['all_nodes'])
        self.assertEqual('[["hostname", "CLUSTER", "test-slave"]]',
                         result['controller_constraints'])
        self.assertEqual('[["hostname", "CLUSTER", "test-slave"]]',
                         result['compute_constraints'])
        self.assertEqual('[["hostname", "CLUSTER", "test-slave"]]',
                         result['controller_compute_constraints'])
        self.assertEqual('[["hostname", "CLUSTER", "test-slave"]]',
                         result['storage_constraints'],)

    @fake_mesos.FakeMesosStateTaggedSlaves()
    def test_get_marathon_framework_without_frm(self):
        result = {}
        configuration.get_marathon_framework(result)
        self.assertEqual('marathon_autodetect',
                         result['marathon_framework'])

    def test_get_marathon_framework_with_frm(self):
        result = {
            'marathon_framework': 'marathon'}
        configuration.get_marathon_framework(result)
        self.assertEqual('marathon', result['marathon_framework'])

    def test_get_marathon_framework_errror(self):
        with mock.patch.object(configuration.mesos_utils,
                               'get_marathon') as m_gm:
            m_gm.return_value = None
            self.assertRaises(exception.UndefinedOption,
                              configuration.get_marathon_framework, {})
