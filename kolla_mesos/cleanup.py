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

from oslo_config import cfg
from oslo_log import log as logging
import paramiko
import retrying

from kolla_mesos import chronos
from kolla_mesos.common import mesos_utils
from kolla_mesos.common import zk_utils
from kolla_mesos import exception
from kolla_mesos import marathon
from kolla_mesos import mesos


CONF = cfg.CONF
CONF.import_group('ssh', 'kolla_mesos.config.ssh')

LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def ssh_conn(hostname):
    ssh_client = paramiko.client.SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    LOG.info("Establishing SSH connection to %s", hostname)
    ssh_client.connect(hostname, username=CONF.ssh.username)
    yield ssh_client
    ssh_client.close()


def execute_command(ssh_client, command):
    _, stdout, stderr = ssh_client.exec_command(command)
    # We have to read the stdout and stderr to ensure that we'll not do
    # anything before command ends its execution.
    stdout.read()
    stderr.read()


@retrying.retry(wait_fixed=5000)
def wait_for_mesos_cleanup():
    """Check whether all tasks in Mesos are exited."""
    mesos_client = mesos.Client()
    tasks = mesos_client.get_tasks()
    if len(tasks) > 0:
        LOG.info("Mesos is still running some tasks. Waiting for their "
                 "exit.")
        raise exception.MesosTasksNotCompleted()


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

    hostnames = mesos_utils.get_slave_hostnames()
    for hostname in hostnames:
        with ssh_conn(hostname) as ssh_client:
            LOG.info("Removing all containers on host %s", hostname)
            execute_command(
                ssh_client,
                'sudo docker rm -f -v $(docker ps -a --format "{{ .Names }}" '
                '| grep mesos-)')
            execute_command(
                ssh_client,
                'while sudo docker ps -a --format "{{ .Names }}" | grep '
                'mesos-; do sleep 1; done')
            LOG.info("Removing all named volumes on host %s", hostname)
            execute_command(
                ssh_client,
                "sudo docker volume rm $(sudo docker volume ls -q | grep -v "
                "zookeeper)")
