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

from kolla_mesos import chronos
from kolla_mesos.common import jinja_utils
from kolla_mesos import exception as e
from kolla_mesos import marathon
from kolla_mesos import mesos

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')


class Client(object):
    def __init__(self, mesos_url=None, marathon_url=None,
                 zookeeper_url=None, chronos_url=None, config_file=None):
        default_configs = [config_file] if config_file else []
        CONF([], project='kolla-mesos', default_config_files=default_configs)

        if mesos_url:
            CONF.mesos.host = mesos_url
        if chronos_url:
            CONF.chronos.host = chronos_url
        if zookeeper_url:
            CONF.zookeeper.host = zookeeper_url
        if marathon_url:
            CONF.marathon.host = marathon_url

        self.chronos = chronos.Client()
        self.marathon = marathon.Client()
        self.mesos = mesos.Client()

    def run_service(self, service, **kwargs):
        pass

    def update_service(self, service, **kwargs):
        pass

    def inspect_service_params(self, service):
        # should we search for service configs?
        conf_paths = []
        return set.union(*[jinja_utils.jinja_find_required_variables(
            conf) for conf in conf_paths])

    def validate_service_params(self, service, **kwagrs):
        expected = self.inspect_service_params(service)
        diff = expected - set(kwagrs)
        if diff:
            raise e.ValidationError(
                'The following variables are not specified: %s.'
                % ', '.join(diff))
