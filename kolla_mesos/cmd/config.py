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

import os
import sys

from kazoo.client import KazooClient
from kazoo import exceptions


def env(name, default=''):
    return os.environ.get(name, default)

ZK_HOSTS = env('ZK_HOSTS')


def tree(zk, path=None):
    if path is None:
        path = '/'

    data, stat = zk.get(path)
    dispaly = '%s (children:%s) (size:%s)' % (path, stat.numChildren,
                                              stat.dataLength)
    if stat.dataLength > 0 and stat.dataLength < 100:
        print('%s: %s' % (dispaly, data.encode('utf-8')))
    else:
        print(dispaly)

    try:
        children = zk.get_children(path)
    except exceptions.NoNodeError:
        return
    for child in children:
        tree(zk, os.path.join(path, child))


def cat(zk, path):
    print(zk.get(path)[0])


def write(zk, path, content):
    zk.ensure_path(path)
    zk.set(path, content)


def main():
    zk = KazooClient(hosts=ZK_HOSTS)
    zk.start()

    if len(sys.argv) > 1:
        cat(zk, sys.argv[1])
    else:
        tree(zk, '/kolla')

    zk.stop()

if __name__ == '__main__':
    main()
