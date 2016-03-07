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

    @fake_mesos.FakeMesosStateSlaves()
    def test_get_number_of_nodes(self):
        CONF.set_override('host', 'http://127.0.0.1:5050', group='mesos')
        controller_nodes, compute_nodes, storage_nodes, all_nodes = \
            mesos_utils.get_number_of_nodes()
        self.assertEqual(controller_nodes, 3)
        self.assertEqual(compute_nodes, 2)
        self.assertEqual(storage_nodes, 2)
        self.assertEqual(all_nodes, 7)
