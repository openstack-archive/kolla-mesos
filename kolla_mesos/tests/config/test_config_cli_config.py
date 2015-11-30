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

from oslo_config import cfg

from kolla_mesos.tests import base


CONF = cfg.CONF
CONF.import_opt('path', 'kolla_mesos.config.config_cli')
CONF.import_opt('show', 'kolla_mesos.config.config_cli')


class TestConfigCliConfig(base.BaseTestCase):

    def test_config_cli(self):
        argv = ['--path', 'test_path', '--show']
        CONF(argv, project='kolla-mesos')
        self.assertEqual(CONF.path, 'test_path')
        self.assertTrue(CONF.show)
