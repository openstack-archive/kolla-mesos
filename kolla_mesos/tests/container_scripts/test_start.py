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

import fixtures
import imp
import json
import mock
import os.path
import sys

from oslotest import base
from zake import fake_client

this_dir = os.path.dirname(sys.modules[__name__].__file__)
kolla_mesos_start = os.path.abspath(
    os.path.join(this_dir, '..', '..', '..',
                 'config', 'kolla_mesos_start.py'))
print(kolla_mesos_start)
start = imp.load_source('kolla_mesos_start', kolla_mesos_start)


class CommandTest(base.BaseTestCase):

    def setUp(self):
        super(CommandTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)

    def test_str_1(self):
        cmd = start.Command('a', {'command': 'true'},
                            self.client)
        self.assertEqual('a "true"', str(cmd))

    def test_str_2(self):
        cmd = start.Command('b', {'command': 'true',
                                  'run_once': True},
                            self.client)
        self.assertEqual('b (run_once) "true"', str(cmd))

    def test_str_3(self):
        cmd = start.Command('c', {'command': 'true',
                                  'run_once': True,
                                  'daemon': True},
                            self.client)
        self.assertEqual('c (run_once, daemon) "true"', str(cmd))

    def test_defaults_1(self):
        data = {'command': 'true'}
        cmd = start.Command('a', data, None)
        self.assertEqual(False, cmd.run_once)
        self.assertEqual(False, cmd.daemon)
        self.assertEqual([], cmd.requires)
        self.assertEqual(None, cmd.init_path)
        self.assertEqual(None, cmd.check_path)
        self.assertEqual(0, cmd.priority)

    def test_cmp_1(self):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        cmd2 = start.Command('b', {'command': 'true',
                                   'daemon': True},
                             self.client)
        self.assertTrue(cmd2 > cmd1)
        self.assertEqual(0, cmd1.priority)
        self.assertEqual(100, cmd2.priority)

    def test_cmp_2(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'requires': ['x', 'y']},
                             self.client)
        cmd2 = start.Command('b', {'command': 'true',
                                   'daemon': True},
                             self.client)
        self.assertTrue(cmd2 > cmd1)
        self.assertEqual(2, cmd1.priority)
        self.assertEqual(100, cmd2.priority)

    def test_requirements_fulfilled_no(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'requires': ['/x', '/y']},
                             self.client)

        self.client.create('/x', 'one', makepath=True)
        self.assertFalse(cmd1.requirements_fulfilled())
        self.assertEqual(1, cmd1.priority)

    def test_requirements_fulfilled_yes(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'requires': ['/x', '/y']},
                             self.client)

        self.client.create('/x', 'one', makepath=True)
        self.client.create('/y', 'one', makepath=True)
        self.assertTrue(cmd1.requirements_fulfilled())
        self.assertEqual(0, cmd1.priority)

    def test_run_always(self):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        with fixtures.FakePopen() as mock_popen:
            cmd1.run()
            cmd1.run()
            self.assertEqual(2, len(mock_popen.procs))

    def test_run_once(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'register': '/z/.done',
                                   'run_once': True},
                             self.client)
        with fixtures.FakePopen() as mock_popen:
            cmd1.run()
            cmd1.run()
            self.assertEqual(1, len(mock_popen.procs))
            self.assertTrue(self.client.exists('/z/.done'))

    def test_already_run(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'register': '/z/.done',
                                   'run_once': True},
                             self.client)
        self.client.create('/z/.done', 'one', makepath=True)
        with fixtures.FakePopen() as mock_popen:
            cmd1.run()
            self.assertEqual(0, len(mock_popen.procs))


@mock.patch.object(start, 'get_groups_and_hostvars')
@mock.patch.object(start, 'write_file')
class GenerateConfigTest(base.BaseTestCase):

    def setUp(self):
        super(GenerateConfigTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        start.GROUP = 'testg'
        start.ROLE = 'testr'

    def test_no_rendering(self, m_wf, m_gar):
        conf = {'afile': {
            'source': 'config/mariadb/templates/galera.cnf.j2',
            'dest': '/etc/mysql_dir/my.cnf',
            'owner': 'mysql',
            'perm': "0600"}}
        m_gar.return_value = {}, {}
        self.client.create('/kolla/config/testg/testr/afile', 'xyz',
                           makepath=True)
        start.generate_config(self.client, conf)
        m_wf.assert_called_once_with(conf['afile'], 'xyz')

    def test_simple_render(self, m_wf, m_gar):
        conf = {'afile': {
            'source': 'config/mariadb/templates/galera.cnf.j2',
            'dest': '/etc/mysql_dir/my.cnf',
            'owner': 'mysql',
            'perm': "0600"}}
        m_gar.return_value = {}, {}
        self.client.create('/kolla/variables/xyz', 'yeah', makepath=True)
        self.client.create('/kolla/config/testg/testr/afile', '{{ xyz }}',
                           makepath=True)
        start.generate_config(self.client, conf)
        m_wf.assert_called_once_with(conf['afile'], 'yeah')

    def test_missing_variable(self, m_wf, m_gar):
        conf = {'afile': {
            'source': 'config/mariadb/templates/galera.cnf.j2',
            'dest': '/etc/mysql_dir/my.cnf',
            'owner': 'mysql',
            'perm': "0600"}}
        m_gar.return_value = {}, {}
        self.client.create('/kolla/config/testg/testr/afile', '{{ xyz }}',
                           makepath=True)
        start.generate_config(self.client, conf)
        m_wf.assert_called_once_with(conf['afile'], '')


@mock.patch.object(start, 'run_commands')
@mock.patch.object(start, 'generate_config')
@mock.patch.object(start, 'register_group_and_hostvars')
class MainTest(base.BaseTestCase):

    def setUp(self):
        super(MainTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        start.GROUP = 'testg'
        start.ROLE = 'testr'

    def test_no_register_if_no_daemon(self, m_rgah, m_gc, m_rc):
        afile = {'source': 'bla/a.cnf.j2',
                 'dest': '/etc/somewhere.foo',
                 'owner': 'appy',
                 'perm': '0600'}
        acmd = {'command': 'true'}
        tconf = {'config': {'testg': {'testr': {'afile': afile}}},
                 'commands': {'testg': {'testr': {'thing': acmd}}}}

        self.client.create('/kolla/config/testg/testg', json.dumps(tconf),
                           makepath=True)

        m_zk_c = mock.MagicMock()
        with mock.patch.object(start, 'zk_connection', m_zk_c):
            m_zk_c.return_value.__enter__.return_value = self.client

            start.main()
            m_gc.assert_called_once_with(self.client,
                                         tconf['config']['testg']['testr'])
            m_rc.assert_called_once_with(self.client,
                                         tconf['commands']['testg']['testr'])
            self.assertEqual([], m_rgah.mock_calls)

    def test_register_if_daemon(self, m_rgah, m_gc, m_rc):
        afile = {'source': 'bla/a.cnf.j2',
                 'dest': '/etc/somewhere.foo',
                 'owner': 'appy',
                 'perm': '0600'}
        acmd = {'command': 'true', 'daemon': True}
        tconf = {'config': {'testg': {'testr': {'afile': afile}}},
                 'commands': {'testg': {'testr': {'thing': acmd}}}}

        self.client.create('/kolla/config/testg/testg', json.dumps(tconf),
                           makepath=True)

        m_zk_c = mock.MagicMock()
        with mock.patch.object(start, 'zk_connection', m_zk_c):
            m_zk_c.return_value.__enter__.return_value = self.client

            start.main()
            m_gc.assert_called_once_with(self.client,
                                         tconf['config']['testg']['testr'])
            m_rc.assert_called_once_with(self.client,
                                         tconf['commands']['testg']['testr'])
            self.assertEqual([mock.call(self.client)], m_rgah.mock_calls)
