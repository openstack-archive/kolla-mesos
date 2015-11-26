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
import json
import logging
import os
import pwd
import re
import socket
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

logging.basicConfig()
LOG = logging.getLogger('%s-%s.start' % (GROUP, ROLE))
LOG.setLevel(logging.INFO)


def jinja_filter_bool(text):
    if not text:
        return False
    if text.lower() in ('true', 'yes'):
        return True
    return False


def jinja_render(name, content, global_config, extra=None):
    variables = global_config
    if extra:
        variables.update(extra)

    myenv = jinja2.Environment(loader=jinja2.DictLoader({name: content}))
    myenv.filters['bool'] = jinja_filter_bool
    return myenv.get_template(name).render(variables)


def jinja_find_required_variables(name, content):
    myenv = jinja2.Environment(loader=jinja2.DictLoader({name: content}))
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
    host = str(socket.gethostbyname(socket.gethostname()))
    path = os.path.join('kolla', 'groups', GROUP)
    zk.retry(zk.ensure_path, path)
    node_id = get_new_node_id(zk, path)
    data = "-".join([host, 'node', str(node_id)])
    LOG.info('%s (%s) joining the %s party' % (host, node_id, GROUP))
    party.Party(zk, path, data).join()


def get_groups_and_hostvars(zk):
    # this returns an odd structure but it so we can re-use the
    # ansible templates.
    hostvars = {}
    groups = {GROUP: []}
    path = os.path.join('kolla', 'groups', GROUP)
    for host in party.Party(zk, path):
        LOG.info('get_groups_and_hostvars %s' % host)
        match = re.match("(\d+.\d+.\d+.\d+)-(\w+)-(\d+)", host)
        if match:
            ip = match.group(1)
            hostvars[ip] = {'ansible_eth0': {'ipv4': {'address': ip}},
                            'ansible_eth1': {'ipv4': {'address': ip}},
                            'role': match.group(2),
                            'id': match.group(3)}
            groups[GROUP].append(ip)

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
    with tempfile.NamedTemporaryFile(prefix='kolla-mesos') as tf:
        tf.write(data)
        try:
            inst_cmd = ' '.join(['sudo', 'install', '-v',
                                 '--no-target-directory',
                                 '--group=%s' % gid, '--mode=%s' % perm,
                                 '--owner=%s' % uid, tf.name, dest])
            subprocess.check_call(inst_cmd, shell=True)
        except subprocess.CalledProcessError as exc:
            LOG.error(exc)
            LOG.exception(inst_cmd)


def generate_config(zk, conf):
    # render what ever templates we can given the variables that are
    # defined. If there is a variable that we need, wait for it to be defined.
    host = str(socket.gethostbyname(socket.gethostname()))
    groups, hostvars = get_groups_and_hostvars(zk)
    variables = {'hostvars': hostvars, 'groups': groups,
                 'inventory_hostname': host,
                 'ansible_hostname': host}

    conf_base_node = os.path.join('kolla', 'config', GROUP, ROLE)
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
                    value, stat = zk.get(os.path.join('kolla', 'variables',
                                                      var))
                except kz_exceptions.NoNodeError:
                    value = ''
                    LOG.error('missing required variable %s' % var)

                if stat.dataLength == 0:
                    value = ''
                    LOG.warn('missing required variable value %s' % var)
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
        self.check_path = cmd.get('register')  # eg. /a/b/c/.done
        self.requires = cmd.get('requires', [])
        self.env = os.environ.copy()
        for ek, ev in six.iteritems(cmd.get('env', {})):
            # make sure they are strings
            self.env[ek] = str(ev)
        if self.check_path:
            self.init_path = os.path.dirname(self.check_path)
        else:
            self.init_path = None
        # the lowest valued entries are retrieved first
        # so run the commands with least requirements and those
        # that are not daemon are needed first.
        self.priority = 0
        self.time_slept = 0
        self.requirements_fulfilled()

    def requirements_fulfilled(self):
        self.priority = min(self.time_slept, 50)
        if self.daemon:
            self.priority = self.priority + 100
        fulfilled = True
        for req in self.requires:
            if not self.zk.retry(self.zk.exists, req):
                LOG.warn('%s is waiting for %s' % (self.name, req))
                fulfilled = False
                self.priority = self.priority + 1
        return fulfilled

    def sleep(self, seconds):
        self.time_slept = self.time_slept + seconds
        time.sleep(seconds)

    def __str__(self):
        def get_true_attrs():
            for attr in ['run_once', 'daemon']:
                if getattr(self, attr):
                    yield attr

        extra = ', '.join(get_true_attrs())
        if extra:
            extra = ' (%s)' % extra
        return '%s%s "%s"' % (
            self.name, extra, self.command)

    def __lt__(self, other):
        return self.priority < other.priority

    def __gt__(self, other):
        return other.__lt__(self)

    def run(self):
        zk = self.zk
        LOG.info('** > Running %s' % self.name)
        if self.run_once:
            def _init_done():
                if not self.check_path:
                    LOG.error('run_once is Ture set but no "register"')
                    sys.exit(1)
                return zk.retry(zk.exists, self.check_path)

            if _init_done():
                LOG.info("Path '%s' exists: skipping command" %
                         self.check_path)
            else:
                LOG.info("Path '%s' does not exists: running command" %
                         self.check_path)
                zk.retry(zk.ensure_path, self.init_path)
                lock = zk.Lock(self.init_path)
                LOG.info("Acquiring lock '%s'" % self.init_path)
                with lock:
                    if not _init_done():
                        self._run_command()
                LOG.info("Releasing lock '%s'" % self.init_path)
        else:
            self._run_command()
        LOG.info('** < Complete %s' % self.name)

    def _run_command(self):
        LOG.debug("Running command: %s" % self.command)
        child_p = subprocess.Popen(self.command, shell=True,
                                   env=self.env)
        child_p.wait()
        if child_p.returncode != 0:
            LOG.error("Command %s non-zero code %s" % (
                self, child_p.returncode))
            sys.exit(1)
        if self.check_path:
            self.zk.retry(self.zk.ensure_path, self.check_path)
            LOG.debug("Command '%s' marked as done" % self.name)


def run_commands(zk, conf):
    LOG.info('run_commands')
    cmdq = queue.PriorityQueue()
    for name, cmd in six.iteritems(conf):
        cmdq.put(Command(name, cmd, zk))

    while not cmdq.empty():
        cmd = cmdq.get()
        if cmd.requirements_fulfilled():
            cmd.run()
        else:
            cmd.sleep(20 / cmdq.qsize())
            cmdq.put(cmd)


def main():
    LOG.info('starting')
    with zk_connection(ZK_HOSTS) as zk:
        service_conf_raw, stat = zk.get(os.path.join('kolla', 'config',
                                                     GROUP, GROUP))
        service_conf = json.loads(service_conf_raw)

        # don't join a Party if this container is not running a daemon
        # process.
        register_group = False
        for cmd in service_conf['commands'][GROUP][ROLE].values():
            if cmd.get('daemon', False):
                register_group = True
        if register_group:
            register_group_and_hostvars(zk)

        generate_config(zk, service_conf['config'][GROUP][ROLE])
        run_commands(zk, service_conf['commands'][GROUP][ROLE])


if __name__ == '__main__':
    main()
