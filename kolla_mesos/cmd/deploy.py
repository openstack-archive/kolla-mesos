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

import argparse
import ConfigParser
import contextlib
import datetime
import errno
import json
import logging
import os
import shutil
import signal
import StringIO
import sys
import tempfile
import time
import yaml

import jinja2
from jinja2 import meta
from kazoo import client
# import requests
# from requests.exceptions import ConnectionError


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

signal.signal(signal.SIGINT, signal.SIG_DFL)


class KollaDirNotFoundException(Exception):
    pass


def jinja_filter_bool(text):
    if not text:
        return False
    if text.lower() in ['true', 'yes']:
        return True
    return False


def jinja_render(fullpath, global_config, extra=None):
    variables = global_config
    if extra:
        variables.update(extra)

    if False:  # debug
        needed = jinja_find_required_variables(fullpath)
        for var in needed:
            if var not in variables:
                LOG.error('%s not in variables, rendering %s' % (
                    var, fullpath))
    myenv = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            os.path.dirname(fullpath)))
    myenv.filters['bool'] = jinja_filter_bool
    return myenv.get_template(os.path.basename(fullpath)).render(variables)


def jinja_find_required_variables(fullpath):
    myenv = jinja2.Environment(loader=jinja2.FileSystemLoader(
        os.path.dirname(fullpath)))
    myenv.filters['bool'] = jinja_filter_bool
    template_source = myenv.loader.get_source(myenv,
                                              os.path.basename(fullpath))[0]
    parsed_content = myenv.parse(template_source)
    return meta.find_undeclared_variables(parsed_content)


def zk_copy_tree(zk, source_path, dest_path):
    for src in os.listdir(source_path):
        src_file = os.path.join(source_path, src)
        if os.path.isdir(src_file):
            zk_copy_tree(zk, src_file,
                         os.path.join(dest_path, src))
        else:
            dest_node = os.path.join(dest_path, src)
            LOG.info('Copying {} to {}'.format(
                src_file, dest_node))
            with open(src_file) as src_fp:
                zk.ensure_path(dest_node)
                zk.set(dest_node, src_fp.read())


@contextlib.contextmanager
def zk_connection(zk_hosts):
    zk = client.KazooClient(hosts=zk_hosts)
    try:
        zk.start()
        yield zk
    finally:
        zk.stop()


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def find_base_dir():
    script_path = os.path.dirname(os.path.realpath(sys.argv[0]))
    if os.path.basename(script_path) == 'cmd':
        return os.path.join(script_path, '..', '..')
    if os.path.basename(script_path) == 'bin':
        return '/usr/share/kolla'
    if os.path.exists(os.path.join(script_path, 'tests')):
        return script_path
    raise KollaDirNotFoundException(
        'I do not know where your Kolla directory is'
    )


def find_config_file(filename):
    filepath = os.path.join('/etc/kolla', filename)
    if os.access(filepath, os.R_OK):
        config_file = filepath
    else:
        config_file = os.path.join(find_base_dir(),
                                   'etc', 'kolla', filename)
    return config_file


def merge_args_and_config(settings_from_config_file):
    parser = argparse.ArgumentParser(description='Kolla build script')

    defaults = {
        "namespace": "kollaglue",
        "tag": "latest",
        "base": "centos",
        "base_tag": "latest",
        "install_type": "binary",
    }
    defaults.update(settings_from_config_file)
    parser.set_defaults(**defaults)

    parser.add_argument('-n', '--namespace',
                        help='Set the Docker namespace name',
                        type=str)
    parser.add_argument('--tag',
                        help='Set the Docker tag',
                        type=str)
    parser.add_argument('-b', '--base',
                        help='The base distro to use when building',
                        type=str)
    parser.add_argument('--base-tag',
                        help='The base distro image tag',
                        type=str)
    parser.add_argument('-t', '--type',
                        help='The method of the Openstack install',
                        type=str,
                        dest='install_type')
    parser.add_argument('--zookeeper-host',
                        help='address:port for zookeeper',
                        type=str)
    parser.add_argument('-d', '--debug',
                        help='Turn on debugging log level',
                        action='store_true')
    parser.add_argument('--template-only',
                        help=("Don't build images. Generate Dockerfile only"),
                        action='store_true')
    parser.add_argument('-p', '--profile',
                        help=('Build a pre-defined set of images, see '
                              '[profiles] section in '
                              '{}'.format(
                                  find_config_file('kolla-build.conf'))),
                        type=str,
                        action='append')

    return vars(parser.parse_args())


class KollaWorker(object):

    def __init__(self, config, profiles):
        self.base_dir = os.path.abspath(find_base_dir())
        self.config_dir = os.path.join(self.base_dir, 'config')
        LOG.debug("Kolla base directory: " + self.base_dir)
        self.namespace = config['namespace']
        self.base = config['base']
        self.install_type = config['install_type']
        self.image_prefix = self.base + '-' + config['install_type'] + '-'
        self.build_config = config
        self.profiles = profiles
        self.required_vars = {}

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = time.time()
        ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='kolla-' + ts)
        # Note "odir" == output directory
        self.config_odir = os.path.join(self.temp_dir, 'config')
        self.marathon_odir = os.path.join(self.temp_dir, 'marathon')
        mkdir_p(self.config_odir)
        mkdir_p(self.marathon_odir)
        LOG.debug('Created output dir: {}'.format(self.temp_dir))

    def set_time(self):
        for root, dirs, files in os.walk(self.config_odir):
            for file_ in files:
                os.utime(os.path.join(root, file_), (0, 0))
            for dir_ in dirs:
                os.utime(os.path.join(root, dir_), (0, 0))
        LOG.debug('Set atime and mtime to 0 for all content in working dir')

    def get_projects(self):
        projects = set()
        for prof in self.build_config.get('profile', ['default']):
            projects |= set(self.profiles[prof].split(','))
        return projects

    def get_jinja_vars(self):
        # order for per-project variables (each overrides the previous):
        # 1. /etc/kolla/globals.yml and passwords.yml
        # 2. config/all.yml
        # 3. config/<project>/defaults/main.yml
        with open(find_config_file('passwords.yml'), 'r') as gf:
            global_vars = yaml.load(gf)
        with open(find_config_file('globals.yml'), 'r') as gf:
            global_vars.update(yaml.load(gf))

        all_yml_name = os.path.join(self.config_dir, 'all.yml')
        jvars = yaml.load(jinja_render(all_yml_name, global_vars))
        jvars.update(global_vars)

        for proj in self.get_projects():
            proj_yml_name = os.path.join(self.config_dir, proj,
                                         'defaults', 'main.yml')
            if os.path.exists(proj_yml_name):
                proj_vars = yaml.load(jinja_render(proj_yml_name, jvars))

                jvars.update(proj_vars)
            else:
                LOG.warn('path missing %s' % proj_yml_name)

        # override node_config_directory to empty
        jvars.update({'node_config_directory': ''})
        return jvars

    def merge_ini_files(self, source_files):
        config_p = ConfigParser.ConfigParser()
        for src_file in source_files:
            if not src_file.startswith('/'):
                src_file = os.path.join(self.base_dir, src_file)
            if not os.path.exists(src_file):
                LOG.warn('path missing %s' % src_file)
                continue
            config_p.read(src_file)
        merged_f = StringIO.StringIO()
        config_p.write(merged_f)
        return merged_f.getvalue()

    def write_config_to_zookeeper(self, zk):
        jinja_vars = self.get_jinja_vars()
        self.required_vars = jinja_vars

        for var in jinja_vars:
            if not jinja_vars[var]:
                LOG.info('empty %s=%s' % (var, jinja_vars[var]))
            if 'image' in var:
                LOG.info('%s=%s' % (var, jinja_vars[var]))

        for proj in self.get_projects():
            proj_dir = os.path.join(self.config_dir, proj)
            if not os.path.exists(proj_dir):
                continue

            conf_path = os.path.join(self.config_dir, proj,
                                     '%s_config.yml' % proj)
            extra = yaml.load(jinja_render(conf_path, jinja_vars))
            for service in extra['config'][proj]:
                # write the config files
                for name, item in extra['config'][proj][service].iteritems():
                    dest_node = os.path.join('kolla', 'config',
                                             proj, service, name)
                    zk.ensure_path(dest_node)

                    if isinstance(item['source'], list):
                        content = self.merge_ini_files(item['source'])
                    else:
                        with open(item['source']) as fp:
                            content = fp.read()
                    zk.set(dest_node, content)

                # write the commands
                for name, item in extra['commands'][proj][service].iteritems():
                    dest_node = os.path.join('kolla', 'commands',
                                             proj, service, name)
                    zk.ensure_path(dest_node)
                    try:
                        zk.set(dest_node, json.dumps(item))
                    except Exception as te:
                        LOG.error('%s=%s -> %s' % (dest_node,
                                                   item, te))

                # 3. do the service's config.json (now KOLLA_CONFIG)
                kc_name = os.path.join(self.config_dir, 'config.json')
                # override container_config_directory
                cont_conf_dir = 'zk://localhost/%s/%s' % (proj, service)
                jinja_vars['container_config_directory'] = cont_conf_dir
                kolla_config = jinja_render(kc_name, jinja_vars)

                # 4. parse the marathon app file and add the KOLLA_CONFIG
                values = {'kolla_config': kolla_config}
                app_file = os.path.join(self.base_dir, 'marathon', proj,
                                        service + '.json.j2')
                content = jinja_render(app_file, jinja_vars,
                                       extra=values)
                dest_file = os.path.join(self.temp_dir, 'marathon', proj,
                                         service + '.json')
                mkdir_p(os.path.dirname(dest_file))
                with open(dest_file, 'w') as f:
                    f.write(content)

    def cleanup(self):
        """Remove temp files"""
        shutil.rmtree(self.temp_dir)

    def write_to_zookeeper(self):
        with zk_connection(self.build_config['zookeeper_host']) as zk:
            # to clean these up, uncomment
            zk.delete('/kolla', recursive=True)

            self.write_config_to_zookeeper(zk)

            filter_out = ['groups', 'hostvars', 'kolla_config',
                          'inventory_hostname']
            for var in self.required_vars:
                if (var in filter_out):
                    LOG.info('set(%s) = %s' % (var, self.required_vars[var]))
                    continue
                var_value = self.required_vars[var]
                if isinstance(self.required_vars[var], dict):
                    var_value = json.dumps(self.required_vars[var])
                var_path = os.path.join('kolla', 'variables', var)
                zk.ensure_path(var_path)
                try:
                    zk.set(var_path, var_value)
                except Exception as te:
                    LOG.error('%s=%s -> %s' % (var_path, var_value, te))


def main():
    # need kolla-build, profiles, globals

    kolla_config = ConfigParser.SafeConfigParser()
    kolla_config.read(find_config_file('kolla-build.conf'))
    build_config = merge_args_and_config(kolla_config.items('kolla-build'))
    if build_config['debug']:
        LOG.setLevel(logging.DEBUG)
    profiles = dict(kolla_config.items('profiles'))

    kolla = KollaWorker(build_config, profiles)
    kolla.setup_working_dir()

    kolla.write_to_zookeeper()

    # start the apps
    # kolla.start()
    # kolla.cleanup()


if __name__ == '__main__':
    main()
