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

from kolla_mesos.config import chronos
from kolla_mesos.config import kolla
from kolla_mesos.config import logging
from kolla_mesos.config import marathon
from kolla_mesos.config import network
from kolla_mesos.config import profiles
from kolla_mesos.config import zookeeper


def list_opts():
    return [
        ('chronos', chronos.chronos_opts),
        ('kolla', kolla.kolla_opts),
        ('marathon', marathon.marathon_opts),
        ('network', network.network_opts),
        ('profiles', profiles.profiles_opts),
        ('zookeeper', zookeeper.zookeeper_opts),
        ('', logging.logging_opts)
    ]
