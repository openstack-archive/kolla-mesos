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
import datetime
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


ZK_HOSTS = None
GROUP = None
ROLE = None
PRIVATE_INTERFACE = None
PUBLIC_INTERFACE = None
ANSIBLE_PRIVATE = None
ANSIBLE_PUBLIC = None
DEPLOYMENT_ID = None


def set_globals():
    global ZK_HOSTS, GROUP, ROLE, PRIVATE_INTERFACE, PUBLIC_INTERFACE
    global ANSIBLE_PRIVATE, ANSIBLE_PUBLIC, DEPLOYMENT_ID
    ZK_HOSTS = os.environ.get('KOLLA_ZK_HOSTS')
    GROUP = os.environ.get('KOLLA_GROUP', 'undefined')
    ROLE = os.environ.get('KOLLA_ROLE', 'undefined')
    PRIVATE_INTERFACE = os.environ.get('KOLLA_PRIVATE_INTERFACE', 'undefined')
    PUBLIC_INTERFACE = os.environ.get('KOLLA_PUBLIC_INTERFACE', 'undefined')
    ANSIBLE_PRIVATE = 'ansible_%s' % PRIVATE_INTERFACE
    ANSIBLE_PUBLIC = 'ansible_%s' % PUBLIC_INTERFACE
    DEPLOYMENT_ID = os.environ.get('KOLLA_DEPLOYMENT_ID', 'undefined')


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


def jinja_render(content, global_config, name='dafault_name', extra=None):
    variables = global_config
    if extra:
        variables.update(extra)

    myenv = jinja2.Environment(loader=jinja2.DictLoader({name: content}))
    myenv.filters['bool'] = jinja_filter_bool
    myenv.filters['regex_replace'] = jinja_regex_replace
    return myenv.get_template(name).render(variables)


def jinja_find_required_variables(content, name='default_name'):
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
            'api_interface': PUBLIC_INTERFACE,
            'role': ROLE,
            'id': str(node_id)}

    LOG.info('%s (%s) joining the %s party', host, node_id, GROUP)
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
            LOG.info('get_groups_and_hostvars %s', host)
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


def generate_host_vars(zk):
    host = str(get_ip_address(PRIVATE_INTERFACE))
    groups, hostvars = get_groups_and_hostvars(zk)
    variables = {'hostvars': hostvars, 'groups': groups,
                 'inventory_hostname': host,
                 'ansible_hostname': host,
                 'deployment_id': DEPLOYMENT_ID,
                 'service_name': ROLE}
    return variables


def render_template(zk, templ, variables, var_names):
    for var in var_names:
        if var not in variables:
            try:
                value, stat = zk.get(os.path.join('kolla', DEPLOYMENT_ID,
                                                  'variables', var))
            except kz_exceptions.NoNodeError:
                value = ''
                LOG.error('missing required variable %s', var)

            if stat.dataLength == 0:
                value = ''
                LOG.warning('missing required variable value %s', var)
            variables[var] = value.encode('utf-8')
    return jinja_render(templ, variables)


def generate_configs(zk, files, conf_base_node):
    """Render and create all config files for this app"""

    variables = generate_host_vars(zk)
    for name, item in six.iteritems(files):
        LOG.debug('Name is: %s, Item is: %s', name, item)
        if name == 'kolla_mesos_start.py':
            continue
        raw_content, stat = zk.get(os.path.join(conf_base_node, name))
        templ = raw_content.encode('utf-8')
        var_names = jinja_find_required_variables(templ, name)
        if not var_names:
            # not a template, doesn't need rendering.
            write_file(item, templ)
            continue

        content = render_template(zk, templ, variables, var_names)
        write_file(item, content)


def generate_main_config(zk, conf):
    """Take the app main config and render it if needed"""

    variables = generate_host_vars(zk)
    templ = conf.encode('utf-8')
    var_names = jinja_find_required_variables(templ)
    if not var_names:
        # not a template, doesn't need rendering.
        return json.loads(conf)

    content = render_template(zk, templ, variables, var_names)
    return json.loads(content)


class Command(object):
    def __init__(self, name, cmd, zk):
        self.raw_conf = cmd
        self.name = name
        self.zk = zk
        self.command = cmd['command']
        self.run_once = cmd.get('run_once', False)
        self.daemon = cmd.get('daemon', False)
        self.check_path = '/kolla/%s/status/%s/%s/.done' % (DEPLOYMENT_ID,
                                                            ROLE, self.name)
        self.requires = ['/kolla/%s/status/%s/.done' % (DEPLOYMENT_ID, req)
                         for req in cmd.get('dependencies', [])]
        self.init_path = os.path.dirname(self.check_path)
        self.proc = None
        self.retries = int(cmd.get('retries', 0))
        if self.daemon:
            self.timeout = -1
        else:
            self.timeout = 120  # for now...
        self.delay = int(cmd.get('delay', 5))
        self.env = os.environ.copy()
        for ek, ev in cmd.get('env', {}).items():
            # make sure they are strings
            self.env[ek] = str(ev)
        self.requirements_fulfilled()

    def requirements_fulfilled(self):
        fulfilled = True
        for req in self.requires:
            if not self.zk.retry(self.zk.exists, req):
                LOG.warning('%s is waiting for %s', self.name, req)
                fulfilled = False
        return fulfilled

    def sleep(self, queue_size, retry=False):
        seconds = math.ceil(20 / (1.0 + queue_size))

        if retry:
            seconds = min(seconds, self.delay)
            LOG.info('Command %s failed, rescheduling, '
                     '%d retries left', self.name, self.retries)
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
        LOG.info('** > Running %s', self.name)
        if self.run_once:
            def _init_done():
                return zk.retry(zk.exists, self.check_path)

            if _init_done():
                LOG.info("Path '%s' exists: skipping command",
                         self.check_path)
            else:
                LOG.info("Path '%s' does not exists: running command",
                         self.check_path)
                zk.retry(zk.ensure_path, self.init_path)
                lock = zk.Lock(self.init_path)
                LOG.info("Acquiring lock '%s'", self.init_path)
                with lock:
                    if not _init_done():
                        result = self._run_command()
                LOG.info("Releasing lock '%s'", self.init_path)
        else:
            result = self._run_command()
        LOG.info('** < Complete %s result: %s', self.name, result)
        return result

    def _run_command(self):
        LOG.debug("Running command: %s", self.command)
        self.retries = self.retries - 1
        self.proc = subprocess.Popen(self.command, shell=True,
                                     env=self.env)
        if self.proc is None:
            LOG.error("Command '%s' failed (proc=None)", self.name)
            return 1

        if self.timeout > 0:
            now = datetime.datetime.now()
            while((datetime.datetime.now() - now).seconds < self.timeout):
                ret = self.proc.poll()
                LOG.debug("Command %s poll ret='%s'", self.name, ret)
                if ret == 0:
                    self.zk.retry(self.zk.ensure_path, self.check_path)
                    LOG.debug("Command '%s' marked as done", self.name)
                if ret is not None:
                    return ret
                time.sleep(10)

            LOG.error("Command failed with timeout (%s seconds)", self.timeout)
            self.kill_process()

        if self.daemon:
            time.sleep(20)
            ret = self.proc.poll()
            LOG.debug("Daemon poll ret='%s'", ret)
            if ret is None:
                self.zk.retry(self.zk.ensure_path, self.check_path)
                LOG.debug("Daemon '%s' marked as running", self.name)
                self.proc.wait()
                ret = self.proc.returncode
            if ret != 0:
                self.zk.retry(self.zk.delete, self.check_path)
            LOG.debug("Command %s ret='%s'", self.name, ret)
            return ret

    def kill_process(self):
        self.proc.terminate()
        time.sleep(3)
        self.proc.kill()
        self.proc.wait()


def run_commands(zk, service_conf, conf_base_node):
    LOG.info('run_commands')
    cmdq = queue.Queue()

    if 'commands' in service_conf:
        conf = service_conf['commands']
        for name, cmd in conf.items():
            cmdq.put(Command(name, cmd, zk))

    if 'service' in service_conf:
        service_conf['service']['daemon']['daemon'] = True
        cmdq.put(Command('daemon', service_conf['service']['daemon'], zk))

    while not cmdq.empty():
        cmd = cmdq.get()
        if cmd.daemon and not cmdq.empty():
            # run the daemon command last
            cmdq.put(cmd)
            continue
        if cmd.requirements_fulfilled():
            if 'files' in cmd.raw_conf:
                generate_configs(zk, cmd.raw_conf['files'], conf_base_node)
            if cmd.run() != 0:
                if cmd.retries > 0:
                    cmd.sleep(cmdq.qsize(), retry=True)
                    cmdq.put(cmd)
                else:
                    # command failed and no retries, so exit.
                    sys.exit(1)
        else:
            cmd.sleep(cmdq.qsize())
            cmdq.put(cmd)


def main():
    set_globals()
    LOG.info('starting')
    with zk_connection(ZK_HOSTS) as zk:
        base_node = os.path.join('/', 'kolla', DEPLOYMENT_ID, 'config')
        conf_base_node = os.path.join(base_node, GROUP, ROLE)
        service_conf_raw, stat = zk.get(conf_base_node)
        service_conf = json.loads(service_conf_raw)

        # don't join a Party if this container is not running a daemon
        # process.
        if 'service' in service_conf:
            register_group_and_hostvars(zk)
            service_conf = generate_main_config(zk, service_conf_raw)
            LOG.debug('Rendered service config: %s', service_conf)

        run_commands(zk, service_conf, conf_base_node)


if __name__ == '__main__':
    main()
