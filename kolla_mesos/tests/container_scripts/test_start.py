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

import copy
import fixtures
import json
from kazoo.recipe import party
import logging
import mock
from zake import fake_client

from kolla_mesos.container_scripts import start
from kolla_mesos.tests import base


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

    def test_str_4(self):
        cmd = start.Command('b', {'command': 'true',
                                  'retries': '3',
                                  'run_once': True},
                            self.client)
        self.assertEqual('b (run_once, retries) "true"', str(cmd))

    def test_defaults_1(self):
        data = {'command': 'true'}
        cmd = start.Command('a', data, None)
        self.assertEqual(False, cmd.run_once)
        self.assertEqual(False, cmd.daemon)
        self.assertEqual([], cmd.requires)
        self.assertIsNone(cmd.init_path)
        self.assertIsNone(cmd.check_path)
        self.assertEqual(0, cmd.priority)

    def test_cmp_1(self):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        cmd2 = start.Command('b', {'command': 'true',
                                   'daemon': True},
                             self.client)
        self.assertTrue(cmd2 > cmd1)
        self.assertEqual(0, cmd1.priority)
        self.assertEqual(101, cmd2.priority)

    def test_cmp_2(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'requires': ['x', 'y']},
                             self.client)
        cmd2 = start.Command('b', {'command': 'true',
                                   'daemon': True},
                             self.client)
        self.assertTrue(cmd2 > cmd1)
        self.assertEqual(2, cmd1.priority)
        self.assertEqual(101, cmd2.priority)

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

    def test_return_non_zero(self):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        with fixtures.FakePopen(lambda _: {'returncode': 3}):
            self.assertEqual(3, cmd1.run())

    def test_return_zero(self):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        with fixtures.FakePopen(lambda _: {'returncode': 0}):
            self.assertEqual(0, cmd1.run())

    def test_sleep_0_q(self):
        cmd = start.Command('a', {'command': 'true'},
                            self.client)
        with mock.patch('time.sleep') as m_sleep:
            cmd.sleep(0)
            m_sleep.assert_called_once_with(20)

    def test_sleep_10_q(self):
        cmd = start.Command('a', {'command': 'true'},
                            self.client)
        with mock.patch('time.sleep') as m_sleep:
            cmd.sleep(10)
            m_sleep.assert_called_once_with(2)

    def test_sleep_retry_1(self):
        cmd = start.Command('a', {'command': 'true'},
                            self.client)
        cmd.delay = 4
        with mock.patch('time.sleep') as m_sleep:
            cmd.sleep(10, retry=True)
            m_sleep.assert_called_once_with(2)

    def test_sleep_retry_2(self):
        cmd = start.Command('a', {'command': 'true'},
                            self.client)
        cmd.delay = 4
        with mock.patch('time.sleep') as m_sleep:
            cmd.sleep(4, retry=True)
            m_sleep.assert_called_once_with(4)


class CmdPriorityTest(base.BaseTestCase):
    scenarios = [
        ('00n0', dict(slept=0, req=0, daemon=False, exp_prio=0)),
        ('90n9', dict(slept=9, req=0, daemon=False, exp_prio=9)),
        ('22n4', dict(slept=2, req=2, daemon=False, exp_prio=4)),
        ('00dd', dict(slept=0, req=0, daemon=True, exp_prio=101)),
        ('bbn', dict(slept=200, req=200, daemon=False, exp_prio=100)),
        ('bbd', dict(slept=200, req=200, daemon=True, exp_prio=101)),
    ]

    def setUp(self):
        super(CmdPriorityTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)

    def test_priority(self):
        cmd = start.Command('a', {'command': 'true'},
                            self.client)
        cmd.time_slept = self.slept
        cmd.num_requires_remaining = self.req
        self.assertEqual(self.exp_prio, cmd.priority)


@mock.patch.object(start.Command, 'run', autospec=True)
@mock.patch.object(start, 'generate_config')
@mock.patch.object(start.sys, 'exit')
class RunCommandsTest(base.BaseTestCase):
    def setUp(self):
        super(RunCommandsTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        start.GROUP = 'testg'
        start.ROLE = 'testr'

    def test_one_good(self, m_exit, m_gc, m_run):
        cmd = {'setup': {
            'run_once': True,
            'register': '/kolla/variables/action/.done',
            'command': 'true'}}

        conf = {'config': {'testg': {'testr': {}}},
                'commands': {'testg': {'testr': cmd}}}
        m_run.return_value = 0
        start.run_commands(self.client, conf)
        m_run.assert_called_once_with(mock.ANY)
        self.assertEqual([], m_exit.mock_calls)

    def test_one_bad(self, m_exit, m_gc, m_run):
        cmd = {'setup': {
            'run_once': True,
            'register': '/kolla/variables/action/.done',
            'command': 'true'}}

        conf = {'config': {'testg': {'testr': {}}},
                'commands': {'testg': {'testr': cmd}}}
        m_run.return_value = 3
        start.run_commands(self.client, conf)
        m_run.assert_called_once_with(mock.ANY)
        self.assertEqual([mock.call(1)], m_exit.mock_calls)

    def test_one_bad_retry(self, m_exit, m_gc, m_run):
        cmd = {'setup': {
            'run_once': True,
            'retries': 2,
            'delay': 0,
            'register': '/kolla/variables/action/.done',
            'command': 'true'}}

        conf = {'config': {'testg': {'testr': {}}},
                'commands': {'testg': {'testr': cmd}}}

        self.returns = 0

        def run_effect(run_self):
            if self.returns == 0:
                self.returns = 1
                return 3
            return 0
        m_run.side_effect = run_effect
        start.run_commands(self.client, conf)
        self.assertEqual(2, len(m_run.mock_calls))
        self.assertEqual([], m_exit.mock_calls)

    def test_daemon_last_lots(self, m_exit, m_gc, m_run):
        conf = {'config': {'testg': {'testr': {}}},
                'commands': {'testg': {'testr': {}}}}
        for cc in range(0, 200):
            cmd = {'c-%d' % cc: {'command': 'true'}}
            conf['commands']['testg']['testr'].update(cmd)

        conf['commands']['testg']['testr'].update(
            {'last': {'daemon': True, 'command': 'true'}})
        exp = conf['commands']['testg']['testr']

        def run_record(run_self):
            print(run_self)
            run_self.time_slept = 120
            if run_self.daemon:
                self.assertEqual(1, len(exp))
            del exp[run_self.name]
            return 0
        m_run.side_effect = run_record

        start.run_commands(self.client, conf)
        self.assertEqual(201, len(m_run.mock_calls))
        self.assertEqual([], m_exit.mock_calls)


@mock.patch.object(start, 'get_ip_address')
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

    def test_no_rendering(self, m_wf, m_gar, m_gip):
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

    def test_simple_render(self, m_wf, m_gar, m_gip):
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

    def test_missing_variable(self, m_wf, m_gar, m_gip):
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
            m_rc.assert_called_once_with(self.client, tconf)
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
            m_rc.assert_called_once_with(self.client, tconf)
            self.assertEqual([mock.call(self.client)], m_rgah.mock_calls)


class LogLevelTest(base.BaseTestCase):
    scenarios = [
        ('info', dict(level='info', expect=logging.INFO)),
        ('debug', dict(level='debug', expect=logging.DEBUG)),
        ('error', dict(level='error', expect=logging.ERROR)),
        ('DeBuG', dict(level='DeBuG', expect=logging.DEBUG)),
        ('INFO', dict(level='INFO', expect=logging.INFO)),
        ('huh', dict(level='huh', expect=logging.INFO)),
    ]

    @mock.patch.object(start.LOG, 'setLevel')
    def test_set_loglevel(self, m_set_l):
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_LOGLEVEL',
                                                     newvalue=self.level))
        start.set_loglevel()
        m_set_l.assert_called_once_with(self.expect)


class HostvarsAndGroupsTest(base.BaseTestCase):

    def setUp(self):
        super(HostvarsAndGroupsTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        start.GROUP = 'testg'
        start.ROLE = 'testr'
        start.PRIVATE_INTERFACE = 'eth1'
        start.PUBLIC_INTERFACE = 'eth0'
        start.ANSIBLE_PRIVATE = 'ansible_eth1'
        start.ANSIBLE_PUBLIC = 'ansible_eth0'

    @mock.patch('socket.gethostname')
    @mock.patch.object(start, 'get_ip_address')
    def test_reg_and_retieve_single(self, m_get_ip, m_gethost):
        m_get_ip.return_value = '1.2.3.4'
        m_gethost.return_value = 'test-hostname'
        start.register_group_and_hostvars(self.client)
        groups, hostvars = start.get_groups_and_hostvars(self.client)
        self.assertEqual({'testg': ['1.2.3.4']}, groups)
        exp = {'ansible_eth0': {'ipv4': {'address': '1.2.3.4'}},
               'ansible_eth1': {'ipv4': {'address': '1.2.3.4'}},
               'ansible_hostname': 'test-hostname',
               'role': 'testr',
               'id': '1'}
        self.assertEqual(exp, hostvars['1.2.3.4'])

    @mock.patch('socket.gethostname')
    @mock.patch.object(start, 'get_ip_address')
    def test_reg_and_retieve_multi(self, m_get_ip, m_gethost):
        m_get_ip.return_value = '1.2.3.4'
        m_gethost.return_value = 'test-hostname'

        # register local host group.
        start.register_group_and_hostvars(self.client)

        # dummy external host registration.
        remote = {'ansible_eth0': {'ipv4': {'address': '4.4.4.4'}},
                  'ansible_eth1': {'ipv4': {'address': '4.4.4.4'}},
                  'ansible_hostname': 'the-other-host',
                  'role': 'testr',
                  'id': '55'}
        party.Party(self.client, '/kolla/groups/testg',
                    json.dumps(remote)).join()

        # make sure this function gets both hosts information.
        groups, hostvars = start.get_groups_and_hostvars(self.client)
        self.assertEqual(sorted(['1.2.3.4', '4.4.4.4']),
                         sorted(groups['testg']))
        exp_local = {'ansible_eth0': {'ipv4': {'address': '1.2.3.4'}},
                     'ansible_eth1': {'ipv4': {'address': '1.2.3.4'}},
                     'ansible_hostname': 'test-hostname',
                     'role': 'testr',
                     'id': '1'}
        self.assertEqual(exp_local, hostvars['1.2.3.4'])
        self.assertEqual(remote, hostvars['4.4.4.4'])
