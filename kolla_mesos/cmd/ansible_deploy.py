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

import os
import sys

# NOTE(nihilifer): We have to import ansible.utils first, because of the
# cilcular import issue in Ansible:
# https://bugzilla.redhat.com/show_bug.cgi?id=1065251
from ansible import utils as ansible_utils  # flake8: noqa
from ansible import callbacks
from ansible import playbook as ansible_playbook
from kolla.cmd import build as kolla_build
from oslo_config import cfg

from kolla_mesos.common import file_utils


CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('network', 'kolla_mesos.config.network')
CONF.import_opt('inventory_path', 'kolla_mesos.config.ansible_cli')


def main():
    CONF(sys.argv[1:], project='kolla-mesos')

    playbook_path = file_utils.find_file('ansible/site.yml')
    kolla_module_path = os.path.join(kolla_build.find_base_dir(),
                                     'ansible/library')

    extra_vars = {
        'network_interface': CONF.network.public_interface,
        'docker_registry': CONF.kolla.registry,
        'docker_namespace': CONF.kolla.namespace,
        'kolla_base_distro': CONF.kolla.base,
        'kolla_install_type': CONF.kolla.install_type,
        'openstack_release': CONF.kolla.tag,
        'docker_common_options': {
            'environment': {
                'KOLLA_CONFIG_STRATEGY': CONF.kolla.config_strategy
            }
        }
    }

    playbook_stats = callbacks.AggregateStats()
    playbook_callbacks = callbacks.PlaybookCallbacks(
        verbose=ansible_utils.VERBOSITY)
    runner_callbacks = callbacks.PlaybookRunnerCallbacks(
        playbook_stats, verbose=ansible_utils.VERBOSITY)

    playbook = ansible_playbook.PlayBook(playbook=playbook_path,
                                         host_list=CONF.inventory_path,
                                         stats=playbook_stats,
                                         callbacks=playbook_callbacks,
                                         runner_callbacks=runner_callbacks,
                                         module_path=kolla_module_path,
                                         extra_vars=extra_vars)
    playbook.run()


if __name__ == '__main__':
    main()
