#!/usr/bin/env python

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

"""
Command-line utility to get the IP address from the newest DHCP lease.

It's written for using with vagrant-hostmanager and vagrant-libvirt plugins.
Vagrant-hostmanager by default fetches only IP addresses from eth0 interfaces
on VM-s. Therefore, the first purpose of this utility is to be able to fetch
the address also from the other interfaces.

Libvirt/virsh only lists all DHCP leases for the given network with timestamps.
DHCP leases have their expiration time, but are not cleaned up after destroying
VM. If someone destroys and sets up the VM with the same hostname, we have
many DHCP leases for the same hostname and we have to look up for timestamp.
That's the second purpose of this script.
"""

import argparse
import operator

import libvirt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('vm_name', help='Name of the virtual machine')

    args = parser.parse_args()
    vm_name = args.vm_name

    conn = libvirt.openReadOnly('qemu:///system')
    network = conn.networkLookupByName('default')
    dhcp_leases = libvirt.virNetwork.DHCPLeases(network)

    vm_dhcp_leases = filter(lambda lease: lease['hostname'] == vm_name,
                            dhcp_leases)

    newest_vm_dhcp_lease = sorted(vm_dhcp_leases,
                                  key=operator.itemgetter('expirytime'),
                                  reverse=True)[0]

    print(newest_vm_dhcp_lease['ipaddr'])


if __name__ == '__main__':
    main()
