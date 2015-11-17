#!/usr/bin/env python

#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# TODO(nihilifer): Contribute to https://github.com/mesosphere/dcos-cli and
# remove this module when possible.

from oslo_config import cfg
import requests
from six.moves.urllib import parse


CONF = cfg.CONF


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

    def add_job(self, job_resource):
        """Add job to Chronos.

        :param job_resource: data about job to run on Chronos
        :type job_resource: dict
        """
        url = self._create_url('scheduler/iso8601')
        response = requests.post(url, data=job_resource,
                                 timeout=CONF.chronos.timeout,
                                 headers={'Content-Type': 'application/json'})

        assert response.status_code == 200

    def get_jobs(self):
        """Get list of running jobs in Chronos"""
        url = self._create_url('scheduler/jobs')
        response = requests.get(url, timeout=CONF.chronos.timeout)

        return response.json()
