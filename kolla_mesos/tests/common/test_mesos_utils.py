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

from kolla_mesos.common import mesos_utils
from kolla_mesos.tests import base
from kolla_mesos.tests.fakes import mesos as fake_mesos


CONF = cfg.CONF
CONF.import_group('mesos', 'kolla_mesos.config.mesos')


class TestMesosUtils(base.BaseTestCase):

    def setUp(self):
        super(TestMesosUtils, self).setUp()
        CONF.set_override('host', 'http://127.0.0.1:5050', group='mesos')

    @fake_mesos.FakeMesosStateTaggedSlaves()
    def test_get_number_of_nodes(self):
        controller_nodes, compute_nodes, storage_nodes, all_nodes = \
            mesos_utils.get_number_of_nodes()
        self.assertEqual(3, controller_nodes)
        self.assertEqual(2, compute_nodes)
        self.assertEqual(2, storage_nodes)
        self.assertEqual(7, all_nodes)

    @fake_mesos.FakeMesosStateFrameworks()
    def test_get_marathon(self):
        marathon_framework = mesos_utils.get_marathon()
        self.assertEqual(marathon_framework, 'marathon_autodetect')
