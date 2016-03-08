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

import itertools
import operator
import re

from oslo_config import cfg
from oslo_log import log as logging
import retrying
import six

from kolla_mesos import chronos
from kolla_mesos.common import docker_utils
from kolla_mesos.common import mesos_utils
from kolla_mesos.common import zk_utils
from kolla_mesos import exception
from kolla_mesos import marathon
from kolla_mesos import mesos


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


@retrying.retry(wait_fixed=5000)
def wait_for_mesos_cleanup():
    """Check whether all tasks in Mesos are exited."""
    mesos_client = mesos.Client()
    tasks = mesos_client.get_tasks()
    if len(tasks) > 0:
        LOG.info("Mesos is still running some tasks. Waiting for their "
                 "exit.")
        raise exception.MesosTasksNotCompleted()


def remove_container(dc, container_name):
    LOG.info("Removing container %s", container_name)
    dc.remove_container(container_name)


# NOTE(nihilifer): Despite the fact that OpenStack community decided to use
# builtins like "map", "filter" etc. directly, without aiming to use lazy
# generators in Python 2.x, here we decided to always use generators in every
# version of Python. Mainly because Mesos cluster may have a lot of containers
# and we would do multiple O(n) operations. Doing all these things lazy
# results in iterating only once on the lists of containers and volumes.
def get_container_names(dc):
    exited_containers = dc.containers(all=True,
                                      filters={'status': 'exited'})
    created_containers = dc.containers(all=True,
                                       filters={'status': 'created'})
    dead_containers = dc.containers(all=True,
                                    filters={'status': 'dead'})

    containers = itertools.chain(exited_containers, created_containers,
                                 dead_containers)
    container_name_lists = six.moves.map(operator.itemgetter('Names'),
                                         containers)
    container_name_lists = six.moves.filter(lambda name_list:
                                            len(name_list) > 0,
                                            container_name_lists)
    container_names = six.moves.map(operator.itemgetter(0),
                                    container_name_lists)
    container_names = six.moves.filter(lambda name: re.search(r'/mesos-',
                                                              name),
                                       container_names)
    return container_names


# NOTE(nihilifer): Mesos doesn't support fully the named volumes which we're
# using. Mesos can run containers with named volume with passing the Docker
# parameters directly, but it doesn't handle any other actions with them.
# That's why currently we're cleaning the containers and volumes by calling
# the Docker API directly.
# TODO(nihilifer): Request/develop the feature of cleaning volumes directly
# in Mesos and Marathon.
# TODO(nihilifer): Support multinode cleanup.
def remove_all_containers(dc):
    """Remove all exited containers which were run by Mesos.

    It's done in order to succesfully remove named volumes.
    """
    container_names = get_container_names(dc)
    for container_name in container_names:
        remove_container(dc, container_name)


def remove_all_volumes(dc):
    """Remove all volumes created for containers run by Mesos."""
    if dc.volumes()['Volumes'] is not None:
        volume_names = six.moves.map(operator.itemgetter('Name'),
                                     dc.volumes()['Volumes'])
        for volume_name in volume_names:
            # TODO(nihilifer): Provide a more intelligent filtering for Mesos
            # infra volumes.
            if 'zookeeper' not in volume_name:
                LOG.info("Removing volume %s", volume_name)
                dc.remove_volume(volume_name)
    else:
            LOG.info("No docker volumes found")


def cleanup():
    LOG.info("Starting cleanup...")
    marathon_client = marathon.Client()
    chronos_client = chronos.Client()

    with zk_utils.connection() as zk:
        zk_utils.clean(zk)
    LOG.info("Starting cleanup of apps")
    marathon_client.remove_all_apps()
    LOG.info("Starting cleanup of groups")
    marathon_client.remove_all_groups()
    LOG.info("Starting cleanup of chronos jobs")
    chronos_client.remove_all_jobs()

    LOG.info("Checking whether all tasks in Mesos are exited")
    wait_for_mesos_cleanup()

    docker_urls = mesos_utils.get_docker_urls()
    for docker_url in docker_urls:
        with docker_utils.DockerClient(base_url=docker_url) as dc:
            LOG.info("Starting cleanup of Docker containers")
            remove_all_containers(dc)
            LOG.info("Starting cleanup of Docker volumes")
            remove_all_volumes(dc)
