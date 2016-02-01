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

import contextlib
import logging
import os
import os.path

from kazoo import client
from kazoo import exceptions
from oslo_config import cfg

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')


def tree(zk, path=None, level=0, pretty=None):
    if path is None:
        path = '/'
    if pretty is None:
        pretty = ''
    name = os.path.basename(path)
    data, stat = zk.get(path)
    dispaly = ' ' * level + '%s %s' % (pretty, name)
    if stat.dataLength > 0:
        print('%s:\t(size:%s)' % (dispaly, stat.dataLength))
    else:
        print(dispaly)

    try:
        children = zk.get_children(path)
    except exceptions.NoNodeError:
        return
    pretty = '\_'
    for child in children:
        tree(zk, os.path.join(path, child), level + 1, pretty)
        pretty = ' _'


def cat(zk, path):
    print(zk.get(path)[0])


def write(zk, path, content):
    zk.ensure_path(path)
    zk.set(path, content)


def copy_tree(zk, source_path, dest_path):
    for src in os.listdir(source_path):
        src_file = os.path.join(source_path, src)
        if os.path.isdir(src_file):
            copy_tree(zk, src_file,
                      os.path.join(dest_path, src))
        else:
            dest_node = os.path.join(dest_path, src)
            LOG.info('Copying {} to {}'.format(
                src_file, dest_node))
            with open(src_file) as src_fp:
                zk.ensure_path(dest_node)
                zk.set(dest_node, src_fp.read())


def clean(zk, path='/kolla'):
    zk.delete(path, recursive=True)


@contextlib.contextmanager
def connection(fake=False):
    if fake:
        from zake import fake_client
        zk = fake_client.FakeClient()
    else:
        zk = client.KazooClient(hosts=CONF.zookeeper.host)
    try:
        zk.start()
        yield zk
    finally:
        zk.stop()
