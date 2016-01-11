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

from kolla_mesos import chronos
from kolla_mesos.common import zk_utils
from kolla_mesos import marathon


def cleanup():
    marathon_client = marathon.Client()
    chronos_client = chronos.Client()

    with zk_utils.connection() as zk:
        zk_utils.clean(zk)
    marathon_client.remove_all_apps()
    marathon_client.remove_all_groups()
    chronos_client.remove_all_jobs()
