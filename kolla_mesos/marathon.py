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

import logging

from dcos import errors
from dcos import marathon
from oslo_config import cfg
import retrying


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

CONF = cfg.CONF


class Client(marathon.Client):
    """Marathon client with parameters from configuration"""

    def __init__(self, *args, **kwargs):
        kwargs['timeout'] = CONF.marathon.timeout
        super(Client, self).__init__(CONF.marathon.host, *args, **kwargs)

    @retrying.retry(stop_max_attempt_number=5, wait_fixed=1000)
    def add_app(self, app_resource):
        app_id = app_resource['id']

        # Check if the app already exists
        try:
            old_app = self.get_app(app_id)
        except errors.DCOSException:
            return super(Client, self).add_app(app_resource)
        else:
            if CONF.force:
                self.remove_app(app_id, force=True)
                return super(Client, self).add_app(app_resource)
            else:
                LOG.info('App %s is already deployed. If you want to '
                         'replace it, please use --force flag.',
                         app_resource['id'])
                return old_app
