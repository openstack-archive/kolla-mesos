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

from kolla_mesos.common import utils
from kolla_mesos import exception

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_group('mesos', 'kolla_mesos.config.mesos')


class Client(object):
    """Class for talking to the Mesos server."""

    def _create_url(self, path, pid=None, query_params=None):
        """Create URL for the specific Mesos API resource.

        :param path: the path to the Mesos API resource
        :type path: str
        :param pid:
        :type pid: str
        :param query_params:
        :type query_params: dict
        """
        url = parse.urljoin(
            'http://' + pid[pid.find('@') + 1:] if pid else CONF.mesos.host,
            path)
        if query_params:
            return parse.urljoin(url, utils.get_query_string(query_params))
        return url

    def get_state(self):
        url = self._create_url('state.json')
        LOG.debug("Requesting current Mesos state via '%s'", url)
        response = requests.get(url, timeout=CONF.mesos.timeout)

        return response.json()

    def get_slave_state(self, slave_pid):
        url = self._create_url('state.json', slave_pid)
        LOG.debug("Requesting current Mesos slave state via '%s'", url)
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

    def get_slaves(self):
        """Get list of registered slaves in Mesos"""
        state = self.get_state()
        slaves = state['slaves']

        return slaves

    def read_file(self, file_path, slave_pid):
        url = self._create_url(
            '/files/read', slave_pid, {'path': file_path, 'offset': 0})
        LOG.debug("Requesting file via '%s'", url)
        response = requests.get(url, timeout=CONF.mesos.timeout)
        try:
            return response.json().get('data', '')
        except ValueError:
            raise exception.KollaNotFoundException(file_path)
