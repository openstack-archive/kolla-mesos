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

from kolla_mesos.common import docker_utils
from kolla_mesos.tests import base


@mock.patch('kolla_mesos.common.docker_utils.docker')
class TestDockerUtils(base.BaseTestCase):
    def _asserts(self, docker_mock):
        docker_mock.Client.assert_called_once_with()
        docker_mock.Client().close.assert_called_once_with()

    def test_contextmanager(self, docker_mock):
        with docker_utils.DockerClient() as dc:
            pass

        self._asserts(docker_mock)

    def test_decorator(self, docker_mock):
        @docker_utils.DockerClient()
        def decorated_function(dc):
            return True

        decorated_function()
        self._asserts(docker_mock)
