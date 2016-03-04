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

import os.path

from kolla_mesos import exception
from kolla_mesos import service_definition
from kolla_mesos.tests import base


class TestInspect(base.BaseTestCase):

    def setUp(self):
        super(TestInspect, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')

    def test_missing_service_dir(self):
        self.assertRaises(exception.KollaDirNotFoundException,
                          service_definition.inspect,
                          'glance/glance-api', 'urg')

    def test_missing_service(self):
        self.assertRaises(exception.KollaFileNotFoundException,
                          service_definition.inspect,
                          'glance/spello-api',
                          self.service_dir)

    def test_normal(self):
        expect = sorted(['controller_nodes', 'memcached_image',
                         'enable_memcached',
                         'memcached_mem', 'memcached_cpus',
                         'deployment_id', 'memcached_tag'])

        info = service_definition.inspect('memcached/memcached',
                                          self.service_dir)
        self.assertEqual(expect, sorted(info['required_variables']))


class TestValidate(base.BaseTestCase):

    def setUp(self):
        super(TestValidate, self).setUp()
        self.service_dir = os.path.join(self.project_dir, 'services')

    def test_missing_service_dir(self):
        self.assertRaises(exception.KollaDirNotFoundException,
                          service_definition.validate,
                          'openstack/glance/glance-api', 'urg')

    def test_missing_service(self):
        self.assertRaises(exception.KollaFileNotFoundException,
                          service_definition.validate,
                          'glance/spello-api',
                          self.service_dir)

    def test_simple(self):
        template = '%s/memcached/memcached.yml.j2' % self.service_dir
        expect = {'memcached/daemon': {
                  'name': 'daemon',
                  'registered_by': 'daemon',
                  'run_by': template,
                  'waiters': {}}}

        deps = service_definition.validate('memcached/memcached',
                                           self.service_dir)
        self.assertEqual(expect, deps)

    def test_with_vars(self):
        template = '%s/horizon/horizon.yml.j2' % self.service_dir
        expect = {'horizon/bootstrap': {
                  'name': 'bootstrap',
                  'registered_by': 'bootstrap',
                  'run_by': template,
                  'waiters': {'daemon': 'horizon/daemon'}},
                  'horizon/daemon': {
                  'name': 'daemon',
                  'registered_by': 'daemon',
                  'run_by': template,
                  'waiters': {}},
                  'memcached/daemon': {
                  'waiters': {'daemon': 'horizon/daemon'}}}

        deps = service_definition.validate(
            'horizon/horizon', self.service_dir,
            variables={'enable_memcached': 'yes'})
        self.assertEqual(expect, deps)
