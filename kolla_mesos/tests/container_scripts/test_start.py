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
import json
from kazoo.recipe import party
import logging
import mock
import os.path
import sys
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
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/t1/testg/testr'))
        start.set_globals()

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

    @mock.patch('socket.gethostname')
    def test_defaults_1(self, m_gethost):
        m_gethost.return_value = 'test-hostname'
        data = {'command': 'true'}
        cmd = start.Command('a', data, None)
        self.assertEqual(False, cmd.run_once)
        self.assertEqual(False, cmd.daemon)
        self.assertEqual([], cmd.requires)
        self.assertEqual(['/kolla/t1/status/global/testr/a',
                          '/kolla/t1/status/test-hostname/testr/a'],
                         cmd.check_paths)

    def test_requirements_fulfilled_no(self):
        cmd1 = start.Command('a', {'command': 'true',
                                   'dependencies': [{
                                       'path': 'q/x'
                                   }, {
                                       'path': 'f/y'
                                   }, {
                                       'path': 'a/b',
                                       'scope': 'local'
                                   }]},
                             self.client)

        self.client.create('/kolla/t1/status/q/x',
                           'done', makepath=True)

        self.assertFalse(cmd1.requirements_fulfilled())

    @mock.patch('socket.gethostname')
    def test_requirements_fulfilled_yes(self, m_gethost):
        m_gethost.return_value = 'test-hostname'
        cmd1 = start.Command('a', {'command': 'true',
                                   'dependencies': [{
                                       'path': 'w/x'
                                   }, {
                                       'path': 'y/l',
                                       'scope': 'local'
                                   }]},
                             self.client)

        self.client.create('/kolla/t1/status/global/w/x',
                           'done', makepath=True)
        self.client.create('/kolla/t1/status/test-hostname/y/l',
                           'done', makepath=True)
        self.assertTrue(cmd1.requirements_fulfilled())

    @mock.patch('subprocess.Popen')
    def test_run_always(self, mock_popen):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        mock_popen.return_value = mock.MagicMock()
        mock_popen.return_value.poll.return_value = 0
        cmd1.run()
        cmd1.run()
        self.assertEqual(2, len(mock_popen.return_value.poll.mock_calls))

    @mock.patch('subprocess.Popen')
    def test_run_once(self, mock_popen):
        cmd1 = start.Command('a', {'command': 'true',
                                   'run_once': True},
                             self.client)
        mock_popen.return_value = mock.MagicMock()
        mock_popen.return_value.poll.return_value = 0
        cmd1.run()
        cmd1.run()
        self.assertEqual(1, len(mock_popen.return_value.poll.mock_calls))
        self.assertEqual(start.CMD_DONE, cmd1.get_state())

    @mock.patch('subprocess.Popen')
    def test_already_run(self, mock_popen):
        cmd1 = start.Command('a', {'command': 'true',
                                   'run_once': True},
                             self.client)
        cmd1.set_state(start.CMD_DONE)
        mock_popen.return_value = mock.MagicMock()
        mock_popen.return_value.poll.return_value = 0
        cmd1.run()
        self.assertEqual(0, len(mock_popen.return_value.poll.mock_calls))

    @mock.patch('subprocess.Popen')
    def test_return_non_zero(self, mock_popen):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        mock_popen.return_value = mock.MagicMock()
        mock_popen.return_value.poll.return_value = 3
        self.assertEqual(3, cmd1.run())

    @mock.patch('subprocess.Popen')
    def test_return_zero(self, mock_popen):
        cmd1 = start.Command('a', {'command': 'true'},
                             self.client)
        mock_popen.return_value = mock.MagicMock()
        mock_popen.return_value.poll.return_value = 0
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


class RunCommandsTest(base.BaseTestCase):
    def setUp(self):
        super(RunCommandsTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/deploy_id/testg/testr'))
        start.set_globals()

    @mock.patch.object(start.Command, 'run', autospec=True)
    @mock.patch.object(start.Command, 'generate_configs', autospec=True)
    @mock.patch.object(start.sys, 'exit')
    def test_one_good(self, m_exit, m_gc, m_run):
        conf = {'commands': {'setup': {
            'run_once': True,
            'command': 'true'}}}

        m_run.return_value = 0
        start.run_commands(self.client, conf)
        m_run.assert_called_once_with(mock.ANY)
        self.assertEqual([], m_exit.mock_calls)

    @mock.patch.object(start.Command, 'run', autospec=True)
    @mock.patch.object(start.Command, 'generate_configs', autospec=True)
    @mock.patch.object(start.sys, 'exit')
    def test_one_bad(self, m_exit, m_gc, m_run):
        conf = {'commands': {'setup': {
            'run_once': True,
            'command': 'true'}}}

        m_run.return_value = 3
        start.run_commands(self.client, conf)
        m_run.assert_called_once_with(mock.ANY)
        self.assertEqual([mock.call(1)], m_exit.mock_calls)

    @mock.patch.object(start.Command, 'run', autospec=True)
    @mock.patch.object(start.Command, 'generate_configs', autospec=True)
    @mock.patch.object(start.sys, 'exit')
    def test_one_bad_retry(self, m_exit, m_gc, m_run):
        conf = {'commands': {'setup': {
            'run_once': True,
            'retries': 2,
            'delay': 0,
            'command': 'true'}}}

        self.returns = 0

        def run_effect(run_self):
            if self.returns == 0:
                self.returns = 1
                return 3
            return 0
        m_run.side_effect = run_effect
        start.run_commands(self.client, conf)
        self.assertEqual([mock.call(mock.ANY), mock.call(mock.ANY)],
                         m_run.mock_calls)
        self.assertEqual([], m_exit.mock_calls)

    @mock.patch.object(start.Command, 'generate_configs', autospec=True)
    @mock.patch.object(start.sys, 'exit')
    def test_daemon_last_lots(self, m_exit, m_gc):
        conf = {'commands': {}}
        for cc in range(0, 99):
            cmd = {'c-%d' % cc: {'command': 'true'}}
            conf['commands'].update(cmd)

        conf['commands'].update(
            {'c-last': {'daemon': True, 'command': 'true'}})

        for cc in range(100, 200):
            cmd = {'c-%d' % cc: {'command': 'true'}}
            conf['commands'].update(cmd)
        exp = conf['commands']

        def run_record(run_self):
            print(run_self)
            run_self.time_slept = 120
            if run_self.daemon:
                self.assertEqual(1, len(exp))
            del exp[run_self.name]
            return 0
        # Mocking Command's method in decorator doesn't work
        with mock.patch.object(start.Command, 'run', autospec=True) as m_run:
            m_run.side_effect = run_record
            start.run_commands(self.client, conf)
            self.assertEqual(200, len(m_run.mock_calls))
            self.assertEqual([], m_exit.mock_calls)


class GenerateConfigTest(base.BaseTestCase):

    def setUp(self):
        super(GenerateConfigTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PRIVATE_INTERFACE',
                                                     newvalue='eth1'))
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PUBLIC_INTERFACE',
                                                     newvalue='eth2'))
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/deploy_id/testg/testr'))
        start.set_globals()

    @mock.patch('time.sleep')
    @mock.patch.object(start.TemplateFunctions, 'get_ip_address')
    @mock.patch.object(start.TemplateFunctions, 'get_groups_and_hostvars')
    @mock.patch.object(start, 'write_file')
    def test_no_rendering(self, m_wf, m_gar, m_gip, m_sleep):
        afile = {'afile': {
            'source': 'config/mariadb/templates/galera.cnf.j2',
            'dest': '/etc/mysql_dir/my.cnf',
            'owner': 'mysql',
            'perm': "0600"}}

        conf = {'commands': {'setup': {
            'command': 'true', 'files': afile}}}

        m_gar.return_value = {}, {}
        self.client.create('/kolla/deploy_id/testg/testr/files/afile', 'xyz',
                           makepath=True)
        start.run_commands(self.client, conf)
        m_wf.assert_called_once_with(afile['afile'], 'xyz')

    @mock.patch('time.sleep')
    @mock.patch.object(start.TemplateFunctions, 'get_ip_address')
    @mock.patch.object(start.TemplateFunctions, 'get_groups_and_hostvars')
    @mock.patch.object(start, 'write_file')
    def test_simple_render(self, m_wf, m_gar, m_gip, m_sleep):
        afile = {'afile': {
            'source': 'config/mariadb/templates/galera.cnf.j2',
            'dest': '/etc/mysql_dir/my.cnf',
            'owner': 'mysql',
            'perm': "0600"}}
        conf = {'commands': {'setup': {
            'command': 'true', 'files': afile}}}
        m_gar.return_value = {}, {}
        self.client.create('/kolla/deploy_id/variables/xyz', 'yeah',
                           makepath=True)
        self.client.create('/kolla/deploy_id/testg/testr/files/afile',
                           '{{ xyz }}', makepath=True)
        start.run_commands(self.client, conf)
        m_wf.assert_called_once_with(afile['afile'], 'yeah')

    @mock.patch('time.sleep')
    @mock.patch.object(start, 'render_template')
    @mock.patch.object(start.TemplateFunctions, 'get_ip_address')
    @mock.patch.object(start.TemplateFunctions, 'get_groups_and_hostvars')
    @mock.patch.object(start, 'write_file')
    def test_missing_variable(self, m_wf, m_gar, m_gip, m_rt, m_sleep):
        afile = {'afile': {
            'source': 'config/mariadb/templates/galera.cnf.j2',
            'dest': '/etc/mysql_dir/my.cnf',
            'owner': 'mysql',
            'perm': "0600"}}
        conf = {'commands': {'setup': {
            'command': 'true', 'files': afile}}}
        m_gar.return_value = {}, {}
        m_rt.return_value = ''
        self.client.create('/kolla/deploy_id/testg/testr/files/afile',
                           '{{ xyz }}', makepath=True)
        start.run_commands(self.client, conf)
        m_wf.assert_called_once_with(afile['afile'], '')

    @mock.patch('subprocess.check_call')
    def test_write_file_no_existing(self, m_call):
        conf = {'source': 'config/mariadb/templates/galera.cnf.j2',
                'dest': '/etc/mysql_dir/my.cnf',
                'owner': 'mysql',
                'perm': "0600"}
        self.assertTrue(start.write_file(conf, 'data'))
        m_call.assert_called_once_with(mock.ANY, shell=True)

    @mock.patch('subprocess.check_call')
    def test_write_file_existing_diff(self, m_call):
        existing_f = self.create_tempfiles([('existing', 'data1')])[0]
        conf = {'source': 'config/mariadb/templates/galera.cnf.j2',
                'dest': existing_f,
                'owner': 'mysql',
                'perm': "0600"}

        self.assertTrue(start.write_file(conf, 'data2'))
        m_call.assert_called_once_with(mock.ANY, shell=True)

    @mock.patch('subprocess.check_call')
    def test_write_file_existing_same(self, m_call):
        existing_f = self.create_tempfiles([('existing', 'data1')])[0]

        conf = {'source': 'config/mariadb/templates/galera.cnf.j2',
                'dest': existing_f,
                'owner': 'mysql',
                'perm': "0600"}
        self.assertFalse(start.write_file(conf, 'data1'))
        self.assertEqual([], m_call.mock_calls)


class MainTest(base.BaseTestCase):

    def setUp(self):
        super(MainTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PRIVATE_INTERFACE',
                                                     newvalue='eth1'))
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PUBLIC_INTERFACE',
                                                     newvalue='eth2'))
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/deploy_id/testg/testr'))
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_ZK_HOSTS',
                                                     newvalue='localhost'))
        start.set_globals()

    @mock.patch.object(start, 'run_commands')
    @mock.patch.object(start.Command, 'generate_configs', autospec=True)
    @mock.patch.object(start, 'register_group_and_hostvars')
    def test_no_register_if_no_daemon(self, m_rgah, m_gc, m_rc):
        afile = {'source': 'bla/a.cnf.j2',
                 'dest': '/etc/somewhere.foo',
                 'owner': 'appy',
                 'perm': '0600'}
        acmd = {'command': 'true', 'files': {'afile': afile}}
        tconf = {'commands': {'thing': acmd}}
        self.client.create('/kolla/deploy_id/testg/testr',
                           json.dumps(tconf), makepath=True)

        m_zk_c = mock.MagicMock()
        with mock.patch.object(start, 'zk_connection', m_zk_c):
            m_zk_c.return_value.__enter__.return_value = self.client

            start.main()
            m_rc.assert_called_once_with(self.client, tconf)
            self.assertEqual([], m_rgah.mock_calls)

    @mock.patch.object(start, 'run_commands')
    @mock.patch.object(start.Command, 'generate_configs', autospec=True)
    @mock.patch.object(start, 'register_group_and_hostvars')
    @mock.patch.object(start, 'generate_main_config')
    def test_register_if_daemon(self, m_gmc, m_rgah, m_gc, m_rc):
        afile = {'source': 'bla/a.cnf.j2',
                 'dest': '/etc/somewhere.foo',
                 'owner': 'appy',
                 'perm': '0600'}
        acmd = {'command': 'true', 'files': {'afile': afile}}
        tconf = {'service': {'daemon': acmd}}
        self.client.create('/kolla/deploy_id/testg/testr',
                           json.dumps(tconf), makepath=True)

        m_gmc.return_value = tconf
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


class TemplateFunctionTest(base.BaseTestCase):

    def setUp(self):
        super(TemplateFunctionTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PRIVATE_INTERFACE',
                                                     newvalue='eth1'))
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PUBLIC_INTERFACE',
                                                     newvalue='eth2'))
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/deploy_id/testg/testr'))
        start.set_globals()

    def test_get_parties(self):
        parties = ['/a/f/z/.party', '/a/b/c/.party',
                   '/a/b/.party', '/a/z/f/.party']
        for p in parties:
            party.Party(self.client, p, p).join()
        tf = start.TemplateFunctions(self.client)
        self.assertEqual(sorted(parties),
                         sorted(tf._get_parties(node='/a')))

    @mock.patch('socket.gethostname')
    @mock.patch.object(start.TemplateFunctions, 'get_ip_address')
    def test_reg_and_retieve_single(self, m_get_ip, m_gethost):
        m_get_ip.return_value = '1.2.3.4'
        m_gethost.return_value = 'test-hostname'
        start.register_group_and_hostvars(self.client)
        tf = start.TemplateFunctions(self.client)
        groups, hostvars = tf.get_groups_and_hostvars()
        self.assertEqual({'testr': ['1.2.3.4']}, groups)
        exp = {'ansible_eth1': {'ipv4': {'address': '1.2.3.4'}},
               'ansible_eth2': {'ipv4': {'address': '1.2.3.4'}},
               'ansible_hostname': 'test-hostname',
               'api_interface': 'eth2'}
        self.assertEqual(exp, hostvars['1.2.3.4'])

    @mock.patch('socket.gethostname')
    @mock.patch.object(start.TemplateFunctions, 'get_ip_address')
    def test_reg_and_retieve_multi(self, m_get_ip, m_gethost):
        m_get_ip.return_value = '1.2.3.4'
        m_gethost.return_value = 'test-hostname'

        # register local host group.
        start.register_group_and_hostvars(self.client)

        # dummy external host registration.
        remote = {'ansible_eth0': {'ipv4': {'address': '4.4.4.4'}},
                  'ansible_eth1': {'ipv4': {'address': '4.4.4.4'}},
                  'ansible_hostname': 'the-other-host',
                  'api_interface': 'eth2'}
        party.Party(self.client, '/kolla/deploy_id/testg/testr/.party',
                    json.dumps(remote)).join()

        # make sure this function gets both hosts information.
        tf = start.TemplateFunctions(self.client)
        groups, hostvars = tf.get_groups_and_hostvars()
        self.assertEqual(sorted(['1.2.3.4', '4.4.4.4']),
                         sorted(groups['testr']))
        exp_local = {'ansible_eth1': {'ipv4': {'address': '1.2.3.4'}},
                     'ansible_eth2': {'ipv4': {'address': '1.2.3.4'}},
                     'ansible_hostname': 'test-hostname',
                     'api_interface': 'eth2'}
        self.assertEqual(exp_local, hostvars['1.2.3.4'])
        self.assertEqual(remote, hostvars['4.4.4.4'])
        ips = tf.list_ips_by_service('testg/testr')
        self.assertIn('1.2.3.4', ips)
        self.assertIn('4.4.4.4', ips)
        ipsp = tf.list_ips_by_service('testg/testr', port='3246')
        self.assertIn('1.2.3.4:3246', ipsp)
        self.assertIn('4.4.4.4:3246', ipsp)


class RenderNovaConfTest(base.BaseTestCase):

    scenarios = [
        ('basic', dict(out='basic')),
        ('vswitch', dict(neutron_plugin_agent='openvswitch', out='vswitch')),
        ('ceph', dict(enable_ceph='yes', out='ceph')),
        ('ironic', dict(enable_ironic='yes', out='ironic'))]

    def setUp(self):
        super(RenderNovaConfTest, self).setUp()
        self.client = fake_client.FakeClient()
        self.client.start()
        self.addCleanup(self.client.stop)
        self.addCleanup(self.client.close)
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PRIVATE_INTERFACE',
                                                     newvalue='eth1'))
        self.useFixture(fixtures.EnvironmentVariable('KOLLA_PUBLIC_INTERFACE',
                                                     newvalue='eth2'))
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/did/openstack/nova/nova-compute'))
        start.set_globals()

    def _register_service(self, service_name, ips):
        for ip in ips:
            remote = {'ansible_eth1': {'ipv4': {'address': ip}},
                      'ansible_eth2': {'ipv4': {'address': ip}},
                      'ansible_hostname': ip,
                      'api_interface': 'eth2'}
            party.Party(self.client,
                        '/kolla/did/%s/.party' % service_name,
                        json.dumps(remote)).join()

    def _define_variables(self):
        variables = {'enable_ironic': 'no',
                     'enable_ceph': 'no',
                     'nova_console': 'yes',
                     'neutron_plugin_agent': 'linuxbridge',
                     'ironic_keystone_user': 'irony',
                     'memcached_port': '1357',
                     'nova_database_name': 'noova',
                     'nova_logging_debug': 'yes',
                     'nova_metadata_port': '4229',
                     'ironic_keystone_password': 'letmein',
                     'nova_api_port': '0987',
                     'rabbitmq_user': 'jump',
                     'glance_api_port': '8776',
                     'nova_database_address': '3.3.3.3',
                     'ironic_api_port': '3085',
                     'nova_keystone_password': 'noo_go',
                     'nova_api_database_name': 'noova_api',
                     'api_interface': 'eth2',
                     'neutron_server_port': '4422',
                     'nova_api_database_password': 'noo',
                     'neutron_keystone_password': 'yees',
                     'nova_novncproxy_port': '3333',
                     'ceph_nova_pool_name': 'fred',
                     'metadata_secret': 'shshsh',
                     'nova_api_database_address': '1.2.3.4',
                     'enable_nova_fake': 'no',
                     'rbd_secret_uuid': '1029384785',
                     'openstack_auth_v2': 'stuff',
                     'nova_database_user': 'nova_dba',
                     'nova_spicehtml5proxy_port': '5503',
                     'kolla_internal_address': '5.5.5.5',
                     'nova_api_ec2_port': '3410',
                     'keystone_admin_port': '2084',
                     'nova_database_password': 'yikes',
                     'keystone_public_port': '1111',
                     'rabbitmq_password': 'jumpforjoy',
                     'rabbitmq_port': '9090',
                     'nova_api_database_user': 'sucker',
                     'marathon_framework': 'mfrm',
                     'mesos_dns_domain': 'mdom',
                     'keystone_auth_host':
                     'keystone-api-keystone-openstack-did.mfrm.mdom',
                     'neutron_server_host':
                     'neutron-server-neutron-openstack-did.mfrm.mdom',
                     'glance_api_host':
                     'glance-api-glance-api-openstack-did.mfrm.mdom',
                     'cinder_api_host':
                     'cinder-api-cinder-openstack-did.mfrm.mdom',
                     'nova_api_host': 'nova-api-nova-openstack-did.mfrm.mdom'}
        for nam, val in variables.items():
            self.client.create('/kolla/did/variables/%s' % nam,
                               getattr(self, nam, val),
                               makepath=True)

    @mock.patch('time.sleep')
    @mock.patch('socket.gethostname')
    @mock.patch.object(start.TemplateFunctions, 'get_ip_address')
    @mock.patch.object(start, 'write_file')
    def test_nova_conf(self, m_write_file, m_get_ip, m_gethost, m_sleep):
        m_get_ip.return_value = '1.2.3.4'
        m_gethost.return_value = 'test-hostname'

        # register local host group.
        start.register_group_and_hostvars(self.client)

        self._register_service('openstack/nova/nova-compute', ['4.4.4.4'])
        self._register_service('infra/memcached/memcached',
                               ['3.1.2.3', '3.1.2.4'])
        self._register_service('infra/rabbitmq/rabbitmq',
                               ['2.1.2.3', '2.1.2.4'])
        self._register_service('openstack/glance/glance-api',
                               ['1.1.2.3', '1.1.2.4'])
        self._define_variables()

        afile = {'source': 'nova.conf.j2',
                 'dest': '/etc/nova/nova.conf',
                 'owner': 'nova',
                 'perm': '0600'}

        conf = {'commands': {'setup': {
            'command': 'true', 'files': {'afile': afile}}}}

        mod_dir = os.path.dirname(sys.modules[__name__].__file__)
        proj_dir = os.path.abspath(os.path.join(mod_dir, '..', '..', '..'))
        with open(os.path.join(proj_dir,
                  'config/nova/templates/nova.conf.j2')) as nc:
            template_contents = nc.read()
            self.client.create(
                '/kolla/did/openstack/nova/nova-compute/files/afile',
                template_contents, makepath=True)

        cmp_file = os.path.join(mod_dir, 'nova-%s.conf' % self.out)
        with open(cmp_file) as cf:
            expect = cf.read()

        start.run_commands(self.client, conf)
        m_write_file.assert_called_once_with(afile, expect)


class GlobalsTest(base.BaseTestCase):
    scenarios = [
        ('1', dict(prefix='/root', app_id='/dep_id/tg/tr', dep_id='dep_id',
                   dep='/root/dep_id', role='tr', sn='tg/tr')),
        ('2', dict(prefix='/root', app_id='/dep_id/openstack/tg/tr',
                   dep_id='dep_id', dep='/root/dep_id', role='tr',
                   sn='openstack/tg/tr')),
        ('3', dict(prefix=None, app_id='/new_id/openstack/tg/tr',
                   dep_id='new_id', dep='/kolla/new_id', role='tr',
                   sn='openstack/tg/tr'))]

    def setUp(self):
        super(GlobalsTest, self).setUp()
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue=self.app_id))
        self.useFixture(fixtures.EnvironmentVariable(
                        'KOLLA_SYSTEM_PREFIX',
                        newvalue=self.prefix))

    def test_globals(self):
        start.set_globals()
        self.assertEqual(self.dep_id, start.DEPLOYMENT_ID)
        self.assertEqual(self.dep, start.DEPLOYMENT)
        self.assertEqual(self.role, start.ROLE)
        self.assertEqual(self.sn, start.SERVICE_NAME)


class CopyAlwaysGlobalTest(base.BaseTestCase):
    scenarios = [
        ('always', dict(strategy='COPY_ALWAYS', expect=True)),
        ('once', dict(strategy='COPY_ONCE', expect=False)),
        ('rubbish', dict(strategy='unexpected', expect=True)),
        ('default', dict(strategy=None, expect=True))]

    def test_strategy(self):
        self.useFixture(fixtures.EnvironmentVariable(
                        'MARATHON_APP_ID',
                        newvalue='/new_id/openstack/tg/tr'))
        self.useFixture(fixtures.EnvironmentVariable(
                        'KOLLA_CONFIG_STRATEGY',
                        newvalue=self.strategy))
        start.set_globals()
        self.assertEqual(self.expect, start.COPY_ALWAYS)
