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

import contextlib
import fcntl
import json
import logging
import math
import os
import pwd
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time

import jinja2
from jinja2 import meta
from kazoo import client as zk_client
from kazoo import exceptions as kz_exceptions
from kazoo.recipe import party
import six
from six.moves import queue


ZK_HOSTS = os.environ.get('KOLLA_ZK_HOSTS')
GROUP = os.environ.get('KOLLA_GROUP', 'mariadb')
ROLE = os.environ.get('KOLLA_ROLE', 'mariadb')
PRIVATE_INTERFACE = os.environ.get('KOLLA_PRIVATE_INTERFACE', 'undefined')
PUBLIC_INTERFACE = os.environ.get('KOLLA_PUBLIC_INTERFACE', 'undefined')
ANSIBLE_PRIVATE = 'ansible_%s' % PRIVATE_INTERFACE
ANSIBLE_PUBLIC = 'ansible_%s' % PUBLIC_INTERFACE
DEPLOYMENT_ID = os.environ.get('KOLLA_DEPLOYMENT_ID', 'undefined')
CMD_WAIT = 'waiting'
CMD_RUN = 'running'
CMD_ERR = 'error'
CMD_RETRY = 'retry'
CMD_DONE = 'done'

logging.basicConfig()
LOG = logging.getLogger(__file__)


def set_loglevel():
    ll = os.environ.get('KOLLA_LOGLEVEL', 'info')
    try:
        nll = getattr(logging, ll.upper(), None)
    except ValueError:
        LOG.exception('Invalid log level: %s' % ll)
        nll = logging.INFO

    if not isinstance(nll, int):
        LOG.error('Invalid log level: %s' % ll)
        nll = logging.INFO
    LOG.setLevel(nll)

set_loglevel()


def jinja_filter_bool(text):
    if not text:
        return False
    if text.lower() in ('true', 'yes'):
        return True
    return False


def jinja_regex_replace(value='', pattern='',
                        replacement='', ignorecase=False):
    if not isinstance(value, basestring):
        value = str(value)

    if ignorecase:
        flags = re.I
    else:
        flags = 0
    _re = re.compile(pattern, flags=flags)
    return _re.sub(replacement, value)


def jinja_render(name, content, global_config, extra=None):
    variables = global_config
    if extra:
        variables.update(extra)

    myenv = jinja2.Environment(loader=jinja2.DictLoader({name: content}))
    myenv.filters['bool'] = jinja_filter_bool
    myenv.filters['regex_replace'] = jinja_regex_replace
    return myenv.get_template(name).render(variables)


def jinja_find_required_variables(name, content):
    myenv = jinja2.Environment(loader=jinja2.DictLoader({name: content}))
    myenv.filters['bool'] = jinja_filter_bool
    myenv.filters['regex_replace'] = jinja_regex_replace
    template_source = myenv.loader.get_source(myenv, name)[0]
    parsed_content = myenv.parse(template_source)
    return meta.find_undeclared_variables(parsed_content)


@contextlib.contextmanager
def zk_connection(zk_hosts):
    zk = zk_client.KazooClient(hosts=zk_hosts)
    try:
        zk.start()
        yield zk
    finally:
        zk.stop()


def get_node_ids(zk, path):
    nodes = set()
    try:
        for i in zk.get_children(path):
            if i.startswith("node-"):
                nodes.add(int(i[5:]))
    except kz_exceptions.NoNodeError:
        pass
    return nodes


def get_new_node_id(zk, path):
    new_id = 1
    obtained = False

    while not obtained:
        nodes = get_node_ids(zk, path)
        while new_id in nodes:
            new_id += 1
        try:
            zk.create(path + '/node-' + str(new_id), ephemeral=True)
            obtained = True
        except Exception:
            continue

    return new_id


def register_group_and_hostvars(zk):
    host = str(get_ip_address(PRIVATE_INTERFACE))
    path = os.path.join('kolla', DEPLOYMENT_ID, 'groups', GROUP)
    zk.retry(zk.ensure_path, path)
    node_id = get_new_node_id(zk, path)

    data = {ANSIBLE_PUBLIC: {'ipv4': {'address':
                                      get_ip_address(PUBLIC_INTERFACE)}},
            ANSIBLE_PRIVATE: {'ipv4': {'address':
                                       get_ip_address(PRIVATE_INTERFACE)}},
            'ansible_hostname': socket.gethostname(),
            'role': ROLE,
            'id': str(node_id)}

    LOG.info('%s (%s) joining the %s party' % (host, node_id, GROUP))
    party.Party(zk, path, json.dumps(data)).join()


def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])


def get_groups_and_hostvars(zk):
    # this returns an odd structure but it so we can re-use the
    # ansible templates.
    hostvars = {}
    groups = {}
    path = os.path.join('kolla', DEPLOYMENT_ID, 'groups')
    for group in zk.get_children(path):
        groups[group] = []
        g_path = os.path.join(path, group)
        for host_data in party.Party(zk, g_path):
            data = json.loads(host_data)
            host = data[ANSIBLE_PRIVATE]['ipv4']['address']
            LOG.info('get_groups_and_hostvars %s' % host)
            groups[group].append(host)
            hostvars[host] = data

    return groups, hostvars


def write_file(conf, data):
    owner = conf.get('owner')
    # Check for user and group id in the environment.
    try:
        uid = pwd.getpwnam(owner).pw_uid
    except KeyError:
        LOG.error('The specified user does not exist: {}'.format(owner))
        sys.exit(1)
    try:
        gid = pwd.getpwnam(owner).pw_gid
    except KeyError:
        LOG.error('The specified group does not exist: {}'.format(owner))
        sys.exit(1)

    dest = conf.get('dest')
    perm = int(conf.get('perm', 0))
    with tempfile.NamedTemporaryFile(prefix='kolla-mesos',
                                     delete=False) as tf:
        tf.write(data)
        tf.flush()
        tf_name = tf.name
    try:
        inst_cmd = ' '.join(['sudo', 'install', '-v',
                             '--no-target-directory',
                             '--group=%s' % gid, '--mode=%s' % perm,
                             '--owner=%s' % uid, tf_name, dest])
        subprocess.check_call(inst_cmd, shell=True)
    except subprocess.CalledProcessError as exc:
        LOG.error(exc)
        LOG.exception(inst_cmd)


def generate_config(zk, conf):
    # render what ever templates we can given the variables that are
    # defined. If there is a variable that we need, wait for it to be defined.
    host = str(get_ip_address(PRIVATE_INTERFACE))
    groups, hostvars = get_groups_and_hostvars(zk)
    variables = {'hostvars': hostvars, 'groups': groups,
                 'inventory_hostname': host,
                 'ansible_hostname': host,
                 'deployment_id': DEPLOYMENT_ID}

    conf_base_node = os.path.join('kolla', DEPLOYMENT_ID, 'config', GROUP,
                                  ROLE)
    for name, item in six.iteritems(conf):
        if name == 'kolla_mesos_start.py':
            continue
        raw_content, stat = zk.get(os.path.join(conf_base_node, name))
        templ = raw_content.encode('utf-8')
        var_names = jinja_find_required_variables(name, templ)
        if not var_names:
            # not a template, doesn't need rendering.
            write_file(item, templ)
            continue

        for var in var_names:
            if var not in variables:
                try:
                    value, stat = zk.get(os.path.join('kolla', DEPLOYMENT_ID,
                                                      'variables', var))
                except kz_exceptions.NoNodeError:
                    value = ''
                    LOG.error('missing required variable %s' % var)

                if stat.dataLength == 0:
                    value = ''
                    LOG.warning('missing required variable value %s' % var)
                variables[var] = value.encode('utf-8')
        content = jinja_render(name, templ, variables)
        write_file(item, content)


class Command(object):
    def __init__(self, name, cmd, zk):
        self.name = name
        self.zk = zk
        self.command = cmd['command']
        self.run_once = cmd.get('run_once', False)
        self.daemon = cmd.get('daemon', False)
        self.check_path = cmd.get('register')  # eg. /a/b/c
        if not self.check_path:
            raise Exception('Command: %s aborted. ' % name +
                            'All commands require a register value')
        self.requires = cmd.get('requires', [])
        self.retries = int(cmd.get('retries', 0))
        self.delay = int(cmd.get('delay', 5))
        self.env = os.environ.copy()

        for ek, ev in cmd.get('env', {}).items():
            # make sure they are strings
            self.env[ek] = str(ev)

    def requirements_fulfilled(self):
        fulfilled = True
        for req in self.requires:
            state = self.get_state(req)
            if state != CMD_DONE:
                LOG.warning('%s is waiting for %s, in state: %s'
                            % (self.name, req, state))
                fulfilled = False
        return fulfilled

    def set_state(self, state):
        self.zk.retry(self.zk.ensure_path, self.check_path)
        current_state, _ = self.zk.get(self.check_path)
        if current_state != state:
            LOG.info('path: %s, changing state from %s to %s'
                     % (self.check_path, current_state, state))
            self.zk.set(self.check_path, state)

    def get_state(self, path=None):
        if not path:
            path = self.check_path
        state = None
        if self.zk.exists(path):
            state, _ = self.zk.get(str(path))
        if not state:
            state = None
        return state

    def sleep(self, queue_size, retry=False):
        seconds = math.ceil(20 / (1.0 + queue_size))

        if retry:
            seconds = min(seconds, self.delay)
            LOG.info('Command %s failed, rescheduling, '
                     '%d retries left' % (self.name, self.retries))
        time.sleep(seconds)

    def __str__(self):
        def get_true_attrs():
            for attr in ['run_once', 'daemon', 'retries']:
                if getattr(self, attr):
                    yield attr

        extra = ', '.join(get_true_attrs())
        if extra:
            extra = ' (%s)' % extra
        return '%s%s "%s"' % (
            self.name, extra, self.command)

    def run(self):
        zk = self.zk
        result = 0
        LOG.info('** > Running %s' % self.name)
        if self.run_once:
            def _init_done():
                if not self.check_path:
                    LOG.error('Run_once is True, but no "register"')
                    sys.exit(1)
                return self.get_state() == CMD_DONE

            if _init_done():
                LOG.info("Path '%s' exists: skipping command" %
                         self.check_path)
            else:
                LOG.info("Path '%s' does not exist: running command" %
                         self.check_path)
                zk.retry(zk.ensure_path, self.check_path)
                lock = zk.Lock(self.check_path)
                LOG.info("Acquiring lock '%s'" % self.check_path)
                with lock:
                    if not _init_done():
                        result = self._run_command()
                LOG.info("Releasing lock '%s'" % self.check_path)
        else:
            result = self._run_command()
        LOG.info('** < Complete %s result: %s' % (self.name, result))
        if result == 0:
            self.set_state(CMD_DONE)
        return result

    def _run_command(self):
        LOG.debug("Running command: %s" % self.command)
        # decrement the retries
        self.retries = self.retries - 1
        self.set_state(CMD_RUN)
        child_p = subprocess.Popen(self.command, shell=True,
                                   env=self.env)
        child_p.wait()
        return child_p.returncode


def run_commands(zk, service_conf):
    LOG.info('run_commands')
    first_ready = False
    conf = service_conf['commands'][GROUP][ROLE]
    cmdq = queue.Queue()
    for name, cmd in conf.items():
        cmdq.put(Command(name, cmd, zk))

    while not cmdq.empty():
        cmd = cmdq.get()
        LOG.debug('evaluating command: %s' % cmd)
        if cmd.daemon and not cmdq.empty():
            # run the daemon command last
            cmd.set_state(CMD_WAIT)
            cmdq.put(cmd)
            continue

        if not cmd.requirements_fulfilled():
            cmd.set_state(CMD_WAIT)
            cmd.sleep(cmdq.qsize())
            cmdq.put(cmd)
        else:
            if not first_ready:
                if ROLE in service_conf['config'][GROUP]:
                    generate_config(zk, service_conf['config'][GROUP][ROLE])
                first_ready = True
            # run the command
            if cmd.run() != 0:
                # command failed
                if cmd.retries > 0:
                    cmd.set_state(CMD_RETRY)
                    cmd.sleep(cmdq.qsize(), retry=True)
                    cmdq.put(cmd)
                else:
                    cmd.set_state(CMD_ERR)
                    LOG.error('exiting start.py due to error...')
                    sys.exit(1)


def main():
    LOG.info('starting deploy id: %s, group: %s' % (DEPLOYMENT_ID, GROUP))
    with zk_connection(ZK_HOSTS) as zk:
        base_node = os.path.join('kolla', DEPLOYMENT_ID)
        zpath = os.path.join(base_node, 'config', GROUP, GROUP)
        if not zk.exists(zpath):
            raise Exception('Aborting start. Path (%s) ' % zpath +
                            'does not exist in zookeeper.')
        service_conf_raw, _ = zk.get(zpath)
        try:
            service_conf = json.loads(service_conf_raw)
        except Exception as e:
            LOG.error('Exception while loading json from zk path: %s' % zpath)
            raise e

        # don't join a Party if this container is not running a daemon
        # process.
        register_group = False
        for cmd in service_conf['commands'][GROUP][ROLE].values():
            if cmd.get('daemon', False):
                register_group = True
        if register_group:
            register_group_and_hostvars(zk)

        run_commands(zk, service_conf)


if __name__ == '__main__':
    main()
