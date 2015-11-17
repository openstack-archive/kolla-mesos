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
import functools
import logging
import os

from six.moves import configparser

from kolla_mesos.cmd import file_utils
from kolla_mesos.cmd import zk_utils

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def merge_args_and_config(settings_from_config_file):
    parser = argparse.ArgumentParser(description='Kolla build script')
    defaults = {
        "zookeeper_host": os.environ.get('ZK_HOSTS', 'localhost:2181'),
    }
    defaults.update(settings_from_config_file)
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


def read_kolla_mesos_config(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        kolla_mesos_config = configparser.SafeConfigParser()
        kolla_mesos_config.read(file_utils.find_config_file(
                                'kolla-mesos.conf'))
        return f(kolla_mesos_config, *args, **kwargs)
    return wrapper


@read_kolla_mesos_config
def read_chronos_config(kolla_mesos_config):
    return dict(kolla_mesos_config.items('chronos'))


def main():

    kolla_config = configparser.SafeConfigParser()
    kolla_config.read(file_utils.find_config_file('kolla-build.conf'))
    config = merge_args_and_config(kolla_config.items('kolla-build'))
    if config['debug']:
        LOG.setLevel(logging.DEBUG)

    with zk_utils.connection(config['zookeeper_host']) as zk:
        if config['show']:
            zk_utils.cat(zk, config['path'])
        else:
            zk_utils.tree(zk, config['path'])

if __name__ == '__main__':
    main()
