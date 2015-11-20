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
import Queue
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


ZK_HOSTS = os.environ.get('KOLLA_ZK_HOSTS')
GROUP = os.environ.get('KOLLA_GROUP', 'mariadb')
ROLE = os.environ.get('KOLLA_ROLE', 'mariadb')

logging.basicConfig()
LOG = logging.getLogger('%s-%s.start' % (GROUP, ROLE))
LOG.setLevel(logging.INFO)


def jinja_filter_bool(text):
    if not text:
        return False
    if text.lower() == 'true':
        return True
    if text.lower() == 'yes':
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
    for name, item in conf.iteritems():
        if name == 'kolla_mesos_start.py':
            continue
        raw_content, stat = zk.get(os.path.join(conf_base_node, name))
        templ = raw_content.encode('utf-8')
        var_names = jinja_find_required_variables(name, templ)
        if not var_names:
            # not a template, doesn't need rendering.
            write_file(item, templ)

        for var in var_names:
            if var not in variables:
                try:
                    value, stat = zk.get(os.path.join('kolla', 'variables',
                                                      var))
                except kz_exceptions.NoNodeError:
                    variables[var] = None
                    LOG.error('missing required variable %s' % var)

                if stat.dataLength == 0:
                    # TODO(asalkeld) missing required variable!
                    variables[var] = None
                    LOG.error('missing required variable %s' % var)
                else:
                    variables[var] = value.encode('utf-8')
        content = jinja_render(name, templ, variables)
        write_file(item, content)


def run_commands(zk, conf):
    LOG.info('run_commands')
    cmdq = Queue.Queue()
    for name, cmd in conf.iteritems():
        cmd['name'] = name
        cmdq.put(cmd)

    while not cmdq.empty():
        cmd = cmdq.get()
        # are requirments fulfilled?
        for req in cmd.get('requires', []):
            if not zk.retry(zk.exists, req):
                LOG.warn('%s is waiting for %s' % (cmd['name'], req))
                # re-queue
                cmdq.put(cmd)
                if cmdq.qsize() == 1:
                    # avoid spinning
                    time.sleep(10)
                continue

        command = cmd['command']
        if cmd.get('run_once', False):
            init_type = 'single'
        else:
            init_type = 'always'
        print('*' * 80)
        print("Running init '%s' (%s), command: %s" % (
              name, init_type, command))
        check_path = cmd.get('register')  # eg. /a/b/c/.done
        if check_path:
            init_path = os.path.dirname(check_path)
        else:
            init_path = None

        def _run_init():
            print("Running init command: %s" % command)
            new_env = os.environ.copy()
            for ek, ev in cmd.get('env', {}).iteritems():
                # make sure they are strings
                new_env[ek] = str(ev)

            print("Running init command: %s env:%s" % (command, new_env))
            child_p = subprocess.Popen(command, shell=True,
                                       env=new_env)
            child_p.wait()
            if child_p.returncode != 0:
                print("Init '%s' (%s), command '%s' non-zero code" % (
                      name, init_type, command, child_p.returncode))
                sys.exit(42)
            if check_path:
                print("Marking init '%s' as done" % name)
                zk.retry(zk.ensure_path, check_path)
                print("Init '%s' marked as done" % name)

        if cmd.get('run_once', False):
            def _init_done():
                if not check_path:
                    LOG.error('run_once set but no "register"')
                    sys.exit(1)
                return zk.retry(zk.exists, check_path)

            if _init_done():
                print("Path '%s' exists: init was already done" % check_path)
                print("Skipping init command")
            else:
                print("Path '%s' not exists: run init" % check_path)
                zk.retry(zk.ensure_path, init_path)
                lock = zk.Lock(init_path)
                print("Acquiring lock '%s'" % init_path)
                with lock:
                    if not _init_done():
                        print("Path '%s' not exists: run init" % check_path)
                        _run_init()
                print("Releasing lock '%s'" % init_path)
        else:
            _run_init()

        print('*' * 80)


def main():
    LOG.info('starting')
    with zk_connection(ZK_HOSTS) as zk:
        register_group_and_hostvars(zk)
        service_conf_raw, stat = zk.get(os.path.join('kolla', 'config',
                                                     GROUP, GROUP))
        service_conf = json.loads(service_conf_raw)
        generate_config(zk, service_conf['config'][GROUP][ROLE])
        run_commands(zk, service_conf['commands'][GROUP][ROLE])


if __name__ == '__main__':
    main()
