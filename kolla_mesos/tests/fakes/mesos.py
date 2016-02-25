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

import functools

from oslo_config import cfg
import requests_mock


CONF = cfg.CONF
CONF.import_group('mesos', 'kolla_mesos.config.mesos')

MESOS_STATE = {
    'slaves': [
        {'attributes': {'openstack_role': 'controller'}},
        {'attributes': {'openstack_role': 'controller'}},
        {'attributes': {'openstack_role': 'controller'}},
        {'attributes': {'openstack_role': 'compute'}},
        {'attributes': {'openstack_role': 'compute'}},
        {'attributes': {'openstack_role': 'storage'}},
        {'attributes': {'openstack_role': 'storage'}}
    ]
}


class FakeMesosStateSlaves(object):
    """Contextmanager and decorator for mocking Mesos API Response.

    This response provides a list of slaves for testing the logic about
    counting the OpenStack nodes.
    """

    def __init__(self):
        self.mocker = requests_mock.mocker.Mocker()
        CONF.set_override('host', 'http://127.0.0.1:5050', group='mesos')

    def __enter__(self):
        self.mocker.start()
        self.mocker.get('http://127.0.0.1:5050/state.json', json=MESOS_STATE)

    def __exit__(self, *args):
        self.mocker.stop()

    def __call__(self, f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with self:
                return f(*args, **kwargs)
        return wrapper
