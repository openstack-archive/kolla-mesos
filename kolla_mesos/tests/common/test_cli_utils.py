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

from kolla_mesos.common import cli_utils
from kolla_mesos.tests import base


class DictToColTest(base.BaseTestCase):
    scenarios = [
        ('normal',
         dict(id_col=None,
              input={'a': 'v1', 'b': 'v2'},
              expect=[('a', 'b'), ('v1', 'v2')])),
        ('special',
         dict(id_col='b',
              input={'a': 'v1', 'b': 'v2'},
              expect=[('b', 'a'), ('v2', 'v1')])),
    ]

    def test_to_col(self):
        self.assertEqual(self.expect,
                         cli_utils.dict2columns(self.input,
                                                id_col=self.id_col))
