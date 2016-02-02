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

from kolla_mesos import cleanup
from kolla_mesos import exception
from kolla_mesos.tests import base


CONF = cfg.CONF
CONF.import_group('mesos', 'kolla_mesos.config.mesos')
CONF.import_opt('workers', 'kolla_mesos.config.multiprocessing_cli')

MESOS_CLEAN_STATE = {'frameworks': [{'tasks': []}]}
MESOS_UNCLEAN_STATE = {'frameworks': [{'tasks': [{'foo': 'bar'}]}]}


class TestMesosCleanup(base.BaseTestCase):

    def setUp(self):
        super(TestMesosCleanup, self).setUp()
        CONF.set_override('host', 'http://localhost:5050', group='mesos')
        CONF.set_override('timeout', 5, group='mesos')

    @requests_mock.mock()
    def test_wait_for_mesos_cleanup_successful(self, req_mock):
        req_mock.get('http://localhost:5050/state.json',
                     json=MESOS_CLEAN_STATE)
        cleanup.wait_for_mesos_cleanup.__wrapped__()

    @requests_mock.mock()
    def test_wait_for_mesos_cleanup_unsuccessful(self, req_mock):
        req_mock.get('http://localhost:5050/state.json',
                     json=MESOS_UNCLEAN_STATE)
        self.assertRaises(exception.MesosTasksNotCompleted,
                          cleanup.wait_for_mesos_cleanup.__wrapped__)


@mock.patch('kolla_mesos.common.docker_utils.docker')
class TestDockerCleanup(base.BaseTestCase):

    def setUp(self):
        super(TestDockerCleanup, self).setUp()
        CONF.set_override('workers', 1)

    def test_remove_container(self, docker_mock):
        cleanup.remove_container('test_container')
        docker_mock.Client().remove_container.assert_called_once_with(
            'test_container')

    def test_get_container_names(self, docker_mock):
        docker_mock.Client().containers.side_effect = [
            [{'Names': ['/mesos-1']}, {'Names': ['/mesos-2']}],
            [{'Names': ['/mesos-3']}], [{'Names': ['/mesos-4']}]
        ]
        container_names = list(cleanup.get_container_names())
        self.assertListEqual(['/mesos-1', '/mesos-2', '/mesos-3', '/mesos-4'],
                             container_names)

    def test_remove_all_volumes(self, docker_mock):
        docker_mock.Client().volumes.return_value = {'Volumes': [
            {'Name': 'test_1'}, {'Name': 'test_2'}
        ]}
        cleanup.remove_all_volumes()
        docker_mock.Client().remove_volume.assert_has_calls(
            [mock.call('test_1'), mock.call('test_2')])
