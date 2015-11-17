#!/usr/bin/python

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

import argparse
import logging
import os

from kolla_mesos.common import config_utils
from kolla_mesos.common import zk_utils


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def merge_args_and_config(settings_from_config_file):
    parser = argparse.ArgumentParser(description='Kolla build script')
    defaults = {
        "zookeeper_host": os.environ.get('ZK_HOSTS', 'localhost:2181'),
    }
    defaults.update(settings_from_config_file.items('kolla-build'))
    parser.set_defaults(**defaults)
    parser.add_argument('--zookeeper-host',
                        help='Zookeeper host:port',
                        type=str)
    parser.add_argument('-d', '--debug',
                        help='Turn on debugging log level',
                        action='store_true')
    parser.add_argument('-s', '--show',
                        help='Show node data',
                        action='store_true')
    parser.add_argument('path',
                        help='Zookeeper node path (try /kolla)')
    return vars(parser.parse_args())


def main():
    cmd_opts, kolla_config = config_utils.load_and_merge('kolla-build.conf',
                                                         merge_args_and_config)

    with zk_utils.connection(cmd_opts['zookeeper_host']) as zk:
        if cmd_opts['show']:
            zk_utils.cat(zk, cmd_opts['path'])
        else:
            zk_utils.tree(zk, cmd_opts['path'])

if __name__ == '__main__':
    main()
