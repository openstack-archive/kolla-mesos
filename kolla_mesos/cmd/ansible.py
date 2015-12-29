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

from ansible import playbook as ansible_playbook
from kolla.cmd import build as kolla_build

from kolla_mesos.common import file_utils


def main():
    playbook_path = file_utils.find_file('ansible/site.yml')
    kolla_module_path = os.path.join(kolla_build.find_base_dir(),
                                     'ansible/library')

    playbook = ansible_playbook.PlayBook(playbook=playbook_path,
                                         module_path=kolla_module_path)
    playbook.run()


if __name__ == '__main__':
    main()
