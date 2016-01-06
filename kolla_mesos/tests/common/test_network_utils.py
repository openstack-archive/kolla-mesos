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
import netifaces
from oslo_config import cfg

from kolla_mesos.common import network_utils
from kolla_mesos.tests import base


CONF = cfg.CONF


class TestNetworkUtils(base.BaseTestCase):

    def test_get_localhost_ipv4(self):
        CONF.set_override('ipv6', False, group='network')
        localhost = network_utils._get_localhost()
        self.assertEqual('127.0.0.1', localhost)

    def test_get_localhost_ipv6(self):
        CONF.set_override('ipv6', True, group='network')
        localhost = network_utils._get_localhost()
        self.assertEqual('::1', localhost)

    @mock.patch('netifaces.interfaces')
    @mock.patch('netifaces.ifaddresses')
    def test_get_ip_address_public_ipv4(self, ifaddresses_mock,
                                        interfaces_mock):
        CONF.set_override('ipv6', False, group='network')
        interfaces_mock.return_value = ['eth2']
        ifaddresses_mock.return_value = {
            netifaces.AF_INET: [{'addr': '10.0.0.1'}]
        }
        ip_address = network_utils.get_ip_address()
        self.assertEqual('10.0.0.1', ip_address)

    @mock.patch('netifaces.interfaces')
    @mock.patch('netifaces.ifaddresses')
    def test_get_ip_address_private_ipv4(self, ifaddresses_mock,
                                         interfaces_mock):
        CONF.set_override('ipv6', False, group='network')
        interfaces_mock.return_value = ['eth1']
        ifaddresses_mock.return_value = {
            netifaces.AF_INET: [{'addr': '10.0.0.1'}]
        }
        ip_address = network_utils.get_ip_address(public=False)
        self.assertEqual('10.0.0.1', ip_address)

    @mock.patch('netifaces.interfaces')
    @mock.patch('netifaces.ifaddresses')
    def test_get_ip_address_public_ipv6(self, ifaddresses_mock,
                                        interfaces_mock):
        CONF.set_override('ipv6', True, group='network')
        interfaces_mock.return_value = ['eth2']
        ifaddresses_mock.return_value = {
            netifaces.AF_INET6: [{'addr': 'fe80::5054:ff:fe80:e42b%eth2'}]
        }
        ip_address = network_utils.get_ip_address()
        self.assertEqual('fe80::5054:ff:fe80:e42b%eth2', ip_address)

    @mock.patch('netifaces.interfaces')
    @mock.patch('netifaces.ifaddresses')
    def test_get_ip_address_private_ipv6(self, ifaddresses_mock,
                                         interfaces_mock):
        CONF.set_override('ipv6', True, group='network')
        interfaces_mock.return_value = ['eth1']
        ifaddresses_mock.return_value = {
            netifaces.AF_INET6: [{'addr': 'fe80::5054:ff:fefc:273e%eth1'}]
        }
        ip_address = network_utils.get_ip_address(public=False)
        self.assertEqual('fe80::5054:ff:fefc:273e%eth1', ip_address)
