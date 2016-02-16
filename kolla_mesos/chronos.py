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

# TODO(nihilifer): Contribute to https://github.com/mesosphere/dcos-cli and
# remove this module when possible.

import json
import operator

from oslo_config import cfg
from oslo_log import log as logging
import requests
from six.moves.urllib import parse

from kolla_mesos.common import retry_utils
from kolla_mesos import exception


LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_group('chronos', 'kolla_mesos.config.chronos')


class Client(object):
    """Class for talking to the Chronos server.

    :param chronos_url: the base URL for the Chronos server
    :type chronos_url: str
    :param timeout: timeout for request to the Chronos server
    :type timeout: int
    """

    def _create_url(self, path):
        """Create URL for the specific Chronos API resource.

        :param path: the path to the Chronos API resource
        :type path: str
        """
        return parse.urljoin(CONF.chronos.host, path)

    @retry_utils.retry_if_not_rollback(stop_max_attempt_number=5,
                                       wait_fixed=1000)
    def add_job(self, job_resource):
        """Add job to Chronos.

        :param job_resource: data about job to run on Chronos
        :type job_resource: dict
        """
        job_name = job_resource['name']

        old_job = self.get_job(job_name)
        if old_job is None:
            url = self._create_url('scheduler/iso8601')
            response = requests.post(url, data=json.dumps(job_resource),
                                     timeout=CONF.chronos.timeout,
                                     headers={'Content-Type':
                                              'application/json'})

            if response.status_code not in [200, 204]:
                raise exception.ChronosException('Failed to add job')
        else:
            if CONF.force:
                LOG.info('Deployment found and --force flag is used. '
                         'Destroying previous deployment and re-creating it.')
                raise exception.ChronosRollback()
            else:
                LOG.info('Job %s is already added. If you want to replace it, '
                         'please use --force flag', job_name)
                return old_job

    def get_job(self, job_name):
        """Get job from Chronos by name.

        :param job_name: id of job to get
        :type job_name: str
        """
        jobs = self.get_jobs()

        return next((job for job in jobs if job['name'] == job_name), None)

    def get_jobs(self):
        """Get list of running jobs in Chronos"""
        LOG.debug('Requesting list of all Chronos jobs')
        url = self._create_url('scheduler/jobs')
        response = requests.get(url, timeout=CONF.chronos.timeout)

        return response.json()

    def remove_job(self, job_name):
        """Remove job from Chronos.

        :param job_name: name of job to delete
        :type job_name: str
        """
        url = self._create_url('scheduler/job/{}'.format(job_name))
        response = requests.delete(url, timeout=CONF.chronos.timeout)

        if response.status_code not in [200, 204]:
            raise exception.ChronosException('Failed to remove job')

    def remove_job_tasks(self, job_name):
        """Remove all tasks for a job.

        :param job_name: name of job to delete tasks from
        :type job_name: str
        """
        url = self._create_url('scheduler/task/kill/{}'.format(job_name))
        response = requests.delete(url, timeout=CONF.chronos.timeout)

        if response.status_code not in [200, 204]:
            raise exception.ChronosException('Failed to remove tasks from job')

    def remove_all_jobs(self, with_tasks=True):
        job_names = list(map(operator.itemgetter('name'), self.get_jobs()))
        LOG.debug('Found chronos jobs: %s', job_names)

        for job_name in job_names:
            if with_tasks:
                LOG.info('Removing chronos job: %s', job_name)
                self.remove_job_tasks(job_name)
            LOG.info('Removing chronos job: %s', job_name)
            self.remove_job(job_name)
