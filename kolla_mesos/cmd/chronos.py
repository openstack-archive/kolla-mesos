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
Command line interface for the Chronos API.
"""

import functools
import sys

from oslo_config import cfg

from kolla_mesos import chronos
from kolla_mesos.common import cli_utils


CONF = cfg.CONF
CONF.import_group('chronos', 'kolla_mesos.config.chronos')
CONF.import_opt('action', 'kolla_mesos.config.chronos_cli')


def chronos_client(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        client = chronos.Client()
        return f(client, *args, **kwargs)
    return wrapper


@chronos_client
def do_list(client):
    jobs = client.get_jobs()
    cli_utils.lister(('Name', 'Mem', 'CPUs', 'Last success', 'Last error',
                      'Command', 'Schedule',),
                     ((job['name'], job['mem'], job['cpus'],
                       job['lastSuccess'], job['lastError'], job['command'],
                       job['schedule'],)
                      for job in jobs))


@chronos_client
def do_show(client):
    job = client.get_job(CONF.action.job_name)
    cli_utils.show(('Name', 'Mem', 'CPUs', 'Disk', 'Last success',
                    'Last error', 'Command', 'Container', 'Environment',),
                   (job['name'], job['mem'], job['cpus'], job['disk'],
                    job['lastSuccess'], job['lastError'], job['command'],
                    job['schedule'], job['container'],
                    job['environmentVariables'],))


def main():
    CONF(sys.argv[1:], project='kolla-mesos')
    function = globals()['do_{}'.format(CONF.action.name)]
    return function()


if __name__ == '__main__':
    main()
