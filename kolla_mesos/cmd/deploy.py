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
import datetime
import json
import logging
import os
import signal
import tempfile
import time

import shutil
from six.moves import configparser
from six.moves import cStringIO
import yaml

from kolla_mesos.common import config_utils
from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import zk_utils


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

signal.signal(signal.SIGINT, signal.SIG_DFL)


class KollaDirNotFoundException(Exception):
    pass


def merge_args_and_config(settings_from_config_file):
    parser = argparse.ArgumentParser(description='Kolla build script')

    defaults = {
        "namespace": "kollaglue",
        "tag": "latest",
        "base": "centos",
        "base_tag": "latest",
        "install_type": "binary",
    }
    defaults.update(settings_from_config_file.items('kolla-build'))
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
                        help='Zookeeper host:port (default localhost:2181)',
                        default="localhost:2181",
                        type=str)
    parser.add_argument('-d', '--debug',
                        help='Turn on debugging log level',
                        action='store_true')
    parser.add_argument('-p', '--profile',
                        help=('Build a pre-defined set of images, see '
                              '[profiles] section in '
                              '{}'.format(
                                  file_utils.find_config_file(
                                      'kolla-build.conf'))),
                        type=str,
                        action='append')

    return vars(parser.parse_args())


class KollaWorker(object):

    def __init__(self, config, profiles):
        self.base_dir = os.path.abspath(file_utils.find_base_dir(
            project='kolla-mesos'))
        self.config_dir = os.path.join(self.base_dir, 'config')
        LOG.debug("Kolla-Mesos base directory: " + self.base_dir)
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
        LOG.debug('Created output dir: {}'.format(self.temp_dir))

    def get_projects(self):
        projects = set()
        for prof in self.build_config.get('profiles', ['default']):
            projects |= set(self.profiles[prof].split(','))
        return projects

    def get_jinja_vars(self):
        # order for per-project variables (each overrides the previous):
        # 1. /etc/kolla/globals.yml and passwords.yml
        # 2. config/all.yml
        # 3. config/<project>/defaults/main.yml
        with open(file_utils.find_config_file('passwords.yml'), 'r') as gf:
            global_vars = yaml.load(gf)
        with open(file_utils.find_config_file('globals.yml'), 'r') as gf:
            global_vars.update(yaml.load(gf))

        all_yml_name = os.path.join(self.config_dir, 'all.yml')
        jvars = yaml.load(jinja_utils.jinja_render(all_yml_name, global_vars))
        jvars.update(global_vars)

        for proj in self.get_projects():
            proj_yml_name = os.path.join(self.config_dir, proj,
                                         'defaults', 'main.yml')
            if os.path.exists(proj_yml_name):
                proj_vars = yaml.load(jinja_utils.jinja_render(proj_yml_name,
                                                               jvars))

                jvars.update(proj_vars)
            else:
                LOG.warn('path missing %s' % proj_yml_name)

        # override node_config_directory to empty
        jvars.update({'node_config_directory': ''})
        return jvars

    def merge_ini_files(self, source_files):
        config_p = configparser.ConfigParser()
        for src_file in source_files:
            if not src_file.startswith('/'):
                src_file = os.path.join(self.base_dir, src_file)
            if not os.path.exists(src_file):
                LOG.warn('path missing %s' % src_file)
                continue
            config_p.read(src_file)
        merged_f = cStringIO.StringIO()
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
                                     '%s_config.yml.j2' % proj)
            extra = yaml.load(jinja_utils.jinja_render(conf_path, jinja_vars))

            dest_node = os.path.join('kolla', 'config',
                                     proj, proj)  # TODO() should be service
            zk.ensure_path(dest_node)
            zk.set(dest_node, json.dumps(extra))

            for service in extra['config'][proj]:
                # write the config files
                for name, item in extra['config'][proj][service].iteritems():
                    dest_node = os.path.join('kolla', 'config',
                                             proj, service, name)
                    zk.ensure_path(dest_node)

                    if isinstance(item['source'], list):
                        content = self.merge_ini_files(item['source'])
                    else:
                        src_file = item['source']
                        if not src_file.startswith('/'):
                            src_file = os.path.join(self.base_dir, src_file)
                        with open(src_file) as fp:
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
                cont_conf_dir = 'zk://%s' % (
                    self.build_config['zookeeper_host'])
                jinja_vars['container_config_directory'] = cont_conf_dir
                kolla_config = jinja_utils.jinja_render(kc_name, jinja_vars)

                # 4. parse the marathon app file and add the KOLLA_CONFIG
                values = {
                    'kolla_config': kolla_config.replace('"', '\\"'),
                    'zookeeper_hosts': self.build_config['zookeeper_host']
                }
                for app_type in ['marathon', 'chronos']:
                    app_file = os.path.join(self.base_dir,
                                            'deployment_files',
                                            proj,
                                            '%s.%s.j2' % (service, app_type))
                    if not os.path.exists(app_file):
                        continue
                    content = jinja_utils.jinja_render(app_file, jinja_vars,
                                                       extra=values)
                    dest_file = os.path.join(self.temp_dir, proj,
                                             '%s.%s' % (service, app_type))
                    file_utils.mkdir_p(os.path.dirname(dest_file))
                    with open(dest_file, 'w') as f:
                        f.write(content)

    def cleanup(self):
        """Remove temp files"""
        shutil.rmtree(self.temp_dir)

    def write_to_zookeeper(self):
        with zk_utils.connection(self.build_config['zookeeper_host']) as zk:
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

    def start(self):
        # find all marathon files and run.
        # find all cronos files and run.
        marathon_api = self.build_config['zookeeper_host'].replace('2181',
                                                                   '8080')
        chronos_api = self.build_config['zookeeper_host'].replace('2181',
                                                                  '4400')
        content_type = '-L -H "Content-type: application/json"'
        for root, dirs, names in os.walk(self.temp_dir):
            for name in names:
                app_path = os.path.join(root, name)
                # this is lazy, I could use requests or the native client.
                if 'marathon' in name:
                    cmd = 'curl -X POST "%s/v2/apps" -d @"%s" %s' % (
                        marathon_api, app_path, content_type)
                else:
                    cmd = 'curl -X POST "%s/scheduler/iso8601" -d @"%s" %s' % (
                        chronos_api, app_path, content_type)
                LOG.info(cmd)


def main():
    cmd_opts, kolla_config = config_utils.load('kolla-build.conf',
                                               merge_args_and_config)
    profiles = dict(kolla_config.items('profiles'))

    kolla = KollaWorker(cmd_opts, profiles)
    kolla.setup_working_dir()
    kolla.write_to_zookeeper()
    kolla.start()

    # kolla.cleanup()


if __name__ == '__main__':
    main()
