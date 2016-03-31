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

import abc
import functools

import requests_mock
import six


MESOS_STATE_TAGGED_SLAVES = {
    'slaves': [
        {'attributes': {'openstack_role': 'controller'},
         'hostname': 'controller01'},
        {'attributes': {'openstack_role': 'controller'},
         'hostname': 'controller02'},
        {'attributes': {'openstack_role': 'controller'},
         'hostname': 'controller03'},
        {'attributes': {'openstack_role': 'compute'},
         'hostname': 'compute01'},
        {'attributes': {'openstack_role': 'compute'},
         'hostname': 'compute01'},
        {'attributes': {'openstack_role': 'storage'},
         'hostname': 'storage01'},
        {'attributes': {'openstack_role': 'storage'},
         'hostname': 'storage02'},
        {'attributes': {'openstack_role': 'all_in_one'},
         'hostname': 'allinone'}
    ],
    'frameworks': [
        {'name': 'chronos_autodetect'},
        {'name': 'marathon_autodetect'},
        {'name': 'another_framework'}
    ]
}
MESOS_STATE_UNTAGGED_SLAVES = {
    'slaves': [
        {'attributes': {},
         'hostname': 'slave01'},
        {'attributes': {},
         'hostname': 'slave02'}
    ]
}
MESOS_STATE_NO_SLAVES = {
    'slaves': []
}
MESOS_STATE_FRAMEWORKS = {
    'frameworks': [
        {'name': 'chronos_autodetect'},
        {'name': 'marathon_autodetect'},
        {'name': 'another_framework'}
    ]
}


@six.add_metaclass(abc.ABCMeta)
class FakeMesosState(object):
    """Contextmanager and decorator for mocking Mesos API Response.

    This response provides a list of slaves for testing the logic about
    counting the OpenStack nodes.
    """
    mesos_state = abc.abstractproperty()

    def __init__(self):
        self.mocker = requests_mock.mocker.Mocker()

    def __enter__(self):
        self.mocker.start()
        self.mocker.get('http://127.0.0.1:5050/state.json',
                        json=self.mesos_state)

    def __exit__(self, *args):
        self.mocker.stop()

    def __call__(self, f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with self:
                return f(*args, **kwargs)
        return wrapper


class FakeMesosStateTaggedSlaves(FakeMesosState):
    mesos_state = MESOS_STATE_TAGGED_SLAVES


class FakeMesosStateUntaggedSlaves(FakeMesosState):
    mesos_state = MESOS_STATE_UNTAGGED_SLAVES


class FakeMesosStateNoSlaves(FakeMesosState):
    mesos_state = MESOS_STATE_NO_SLAVES


class FakeMesosStateFrameworks(FakeMesosState):
    mesos_state = MESOS_STATE_FRAMEWORKS
