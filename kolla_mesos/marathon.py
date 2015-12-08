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
import operator

from dcos import errors as dcos_exc
from dcos import marathon
from oslo_config import cfg
import six

from kolla_mesos.common import retry_utils
from kolla_mesos import exception as kolla_mesos_exc


LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

CONF = cfg.CONF
CONF.import_group('marathon', 'kolla_mesos.config.marathon')


class Client(marathon.Client):
    """Marathon client with parameters from configuration"""

    def __init__(self, *args, **kwargs):
        kwargs['timeout'] = CONF.marathon.timeout
        super(Client, self).__init__(CONF.marathon.host, *args, **kwargs)

    @retry_utils.retry_if_not_rollback(stop_max_attempt_number=5,
                                       wait_fixed=1000)
    def add_app(self, app_resource):
        app_id = app_resource['id']

        # Check if the app already exists
        try:
            old_app = self.get_app(app_id)
        except dcos_exc.DCOSException:
            return super(Client, self).add_app(app_resource)
        else:
            if CONF.force:
                LOG.info('Deployment found and --force flag is used. '
                         'Destroying current deployment and re-creating it.')
                raise kolla_mesos_exc.MarathonRollback()
            else:
                LOG.info('App %s is already deployed. If you want to '
                         'replace it, please use --force flag.', app_id)
                return old_app

    def remove_all_apps(self):
        apps_ids = six.moves.map(operator.itemgetter('id'), self.get_apps())
        for app_id in apps_ids:
            self.remove_app(app_id, force=True)
