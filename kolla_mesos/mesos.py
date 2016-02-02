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
from oslo_log import log as logging
import requests
from six.moves.urllib import parse


LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_group('mesos', 'kolla_mesos.config.mesos')


class Client(object):
    """Class for talking to the Mesos server."""

    def _create_url(self, path):
        """Create URL for the specific Mesos API resource.

        :param path: the path to the Mesos API resource
        :type path: str
        """
        return parse.urljoin(CONF.mesos.host, path)

    def get_state(self):
        url = self._create_url('state.json')
        response = requests.get(url, timeout=CONF.mesos.timeout)

        return response.json()

    def get_frameworks(self):
        state = self.get_state()
        return state['frameworks']

    def get_tasks(self):
        """Get list of running tasks in Mesos"""
        frameworks = self.get_frameworks()
        tasks = []

        for framework in frameworks:
            tasks.extend(framework['tasks'])

        return tasks
