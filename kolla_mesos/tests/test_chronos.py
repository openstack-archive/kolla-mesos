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

from oslotest import base
import requests_mock

from kolla_mesos import chronos
from kolla_mesos.tests import configparser_mock

CHRONOS_CONF = """
[chronos]
url = http://localhost:4400
timeout = 5
"""
EXAMPLE_CHRONOS_JOB = {
    "name": "/keystone-bootstrap",
    "mem": 32.0,
    "cpus": 0.3,
    "container": {
        "type": "DOCKER",
        "image": "/--kolla_ansible:",
        "network": "HOST"
    },
    "environmentVariables": [
        {"name": "KOLLA_CONFIG_STRATEGY", "value": "COPY_ONCE"},
        {"name": "KOLLA_CONFIG", "value": {
            "command": "/usr/local/bin/kolla_mesos_start",
            "config_files": [{
                "source": ("zk://localhost:2181/kolla/config/mariadb/mariadb/"
                           "kolla_mesos_start.py"),
                "dest": "/usr/local/bin/kolla_mesos_start",
                "owner": "root",
                "perm": "0755"
            }]
        }},
        {"name": "KOLLA_GROUP", "value": "keystone"},
        {"name": "KOLLA_ROLE", "value": "keystone_bootstrap"},
        {"name": "KOLLA_ZK_HOSTS", "value": "localhost:2181"}
    ]
}


class TestClient(base.BaseTestCase):

    @configparser_mock.configparser_mock(CHRONOS_CONF)
    def setUp(self):
        super(TestClient, self).setUp()
        self.client = chronos.create_client()

    def test_create_client(self):
        self.assertIsInstance(self.client, chronos.Client)

    def test_create_url(self):
        url = self.client._create_url('test')
        self.assertEqual(url, 'http://localhost:4400/test')

    @requests_mock.mock()
    def test_add_job(self, req_mock):
        req_mock.post('http://localhost:4400/scheduler/iso8601')
        self.client.add_job(EXAMPLE_CHRONOS_JOB)

    @requests_mock.mock()
    def test_get_jobs(self, req_mock):
        req_mock.get('http://localhost:4400/scheduler/jobs',
                     json=[EXAMPLE_CHRONOS_JOB])
        response = self.client.get_jobs()

        self.assertIsInstance(response, list)

        job = response[0]

        self.assertIsInstance(job, dict)
        self.assertDictEqual(job, EXAMPLE_CHRONOS_JOB)
