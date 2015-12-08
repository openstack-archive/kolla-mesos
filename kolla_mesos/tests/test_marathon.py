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

from dcos import errors
import mock
from oslo_config import cfg
import requests_mock

from kolla_mesos import marathon
from kolla_mesos.tests import base


CONF = cfg.CONF


def add_app(app):
    return app


class TestMarathonClient(base.BaseTestCase):

    @requests_mock.mock()
    def setUp(self, req_mock):
        super(TestMarathonClient, self).setUp()
        CONF.set_override('host', 'http://127.0.0.1:8080', group='marathon')
        req_mock.get('http://127.0.0.1:8080/v2/info', json={
            'version': '0.11.0'
        })
        self.client = marathon.Client()

    @mock.patch('dcos.marathon.Client.add_app')
    def test_add_app(self, dcos_add_app_mock):
        dcos_add_app_mock.side_effect = add_app

        with mock.patch.object(
            self.client, 'get_app', side_effect=errors.DCOSException()
        ):
            app = self.client.add_app({'id': 'my-new-app'})

        self.assertDictEqual(app, {'id': 'my-new-app'})

    @mock.patch.object(marathon, 'LOG')
    def test_add_app_already_existing(self, log_mock):
        with mock.patch.object(
            self.client, 'get_app', return_value={'id': 'my-app',
                                                  'other_param': 'the-old-one'}
        ):
            app = self.client.add_app({'id': 'my-app',
                                       'other_param': 'the-new-one'})

        self.assertDictEqual(app, {'id': 'my-app',
                                   'other_param': 'the-old-one'})
        log_mock.info.assert_called_with('App %s is already deployed. '
                                         'If you want to replace it, please '
                                         'use --force flag.', 'my-app')

    @mock.patch('dcos.marathon.Client.add_app')
    def test_add_app_already_existing_force(self, dcos_add_app_mock):
        CONF.set_override('force', True)
        dcos_add_app_mock.side_effect = add_app

        with base.nested(mock.patch.object(
            self.client, 'get_app', return_value={'id': 'my-app',
                                                  'other_param': 'the-old-one'}
        ), mock.patch.object(self.client, 'remove_app')):
            app = self.client.add_app({'id': 'my-app',
                                       'other_param': 'the-new-one'})

        self.assertDictEqual(app, {'id': 'my-app',
                                   'other_param': 'the-new-one'})
