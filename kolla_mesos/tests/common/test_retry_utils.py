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

from kolla_mesos.common import retry_utils
from kolla_mesos import exception
from kolla_mesos.tests import base


class TestRetryUtils(base.BaseTestCase):

    def test_retry_if_not_rollback(self):
        self.assertTrue(retry_utils.retry_if_not_rollback(Exception()))
        self.assertTrue(retry_utils.retry_if_not_rollback(OSError()))
        self.assertFalse(retry_utils.retry_if_not_rollback(
            exception.MarathonRollback()))
