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

from cliff import lister
from cliff import show
from oslo_config import cfg

from kolla_mesos import chronos


CONF = cfg.CONF
CONF.import_group('chronos', 'kolla_mesos.config.chronos')


class List(lister.Lister):
    """List Chronos jobs."""

    def get_parser(self, prog_name):
        parser = super(List, self).get_parser(prog_name)
        parser.add_argument('--path',
                            default='/kolla/%s' % CONF.kolla.deployment_id)
        return parser

    def take_action(self, parsed_args):
        client = chronos.Client()
        jobs = client.get_jobs()
        return (('Name', 'Mem', 'CPUs', 'Last success', 'Last error',
                 'Command', 'Schedule',),
                ((job['name'], job['mem'], job['cpus'],
                  job['lastSuccess'], job['lastError'], job['command'],
                  job['schedule'],)
                 for job in jobs))


class Show(show.ShowOne):
    """Show the chronos job."""

    def get_parser(self, prog_name):
        parser = super(Show, self).get_parser(prog_name)
        parser.add_argument('job_name')
        return parser

    def take_action(self, parsed_args):
        client = chronos.Client()
        job_name = "%s-%s" % (CONF.kolla.deployment_id, parsed_args.job_name)
        job = client.get_job(job_name)
        return (('Name', 'Mem', 'CPUs', 'Disk', 'Last success',
                 'Last error', 'Command', 'Container', 'Environment',),
                (job['name'], job['mem'], job['cpus'], job['disk'],
                 job['lastSuccess'], job['lastError'], job['command'],
                 job['schedule'], job['container'],
                 job['environmentVariables'],))
