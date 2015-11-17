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

import urllib

from oslo_config import cfg
import requests


CHRONOS_OPTS = [
    cfg.StrOpt('url', default='http://localhost:4400',
               help='URL to the Chronos server'),
    cfg.IntOpt('timeout', default=http.DEFAULT_TIMEOUT,
               help='Timeout for request to the Chronos server')
]


CONF = cfg.CONF
chronos_opt_group = cfg.OptGroup(name='chronos',
                                 title='Options for the Chronos client')
CONF.register_group(chronos_opt_group)
CONF.register_opts(CHRONOS_OPTS, chronos_opt_group)


def create_client():
    return Client(CONF.chronos.url, CONF.chronos.timeout)


class Client(object):
    """Class for talking to the Chronos server.

    :param chronos_url: the base URL for the Chronos server
    :type chronos_url: str
    """

    def __init__(self, chronos_url, timeout=http.DEFAULT_TIMEOUT):
        self._base_url = chronos_url
        self._timeout = timeout

    def _create_url(self, path):
        return urllib.parse.urljoin(self._base_url, path)

    def add_job(self, job_resource):
        url = self._create_url('scheduler/iso8601')
        response = requests.post(url, data=job_resource, timeout=self._timeout)

        return response.json()

    def get_jobs(self):
        url = self._create_url('scheduler/jobs')
        response = requests.get(url, timeout=self._timeout)

        return response.json()
