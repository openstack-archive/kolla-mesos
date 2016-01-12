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

import copy
import datetime
import json
import logging
import os
import signal
import sys
import tempfile
import time

from oslo_config import cfg
import retrying
import shutil
from six.moves import configparser
from six.moves import cStringIO
import yaml

from kolla_mesos import chronos
from kolla_mesos import cleanup
from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import zk_utils
from kolla_mesos import exception
from kolla_mesos import marathon


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

signal.signal(signal.SIGINT, signal.SIG_DFL)

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('profiles', 'kolla_mesos.config.profiles')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')
CONF.import_opt('update', 'kolla_mesos.config.deploy_cli')
CONF.import_opt('force', 'kolla_mesos.config.deploy_cli')


class KollaDirNotFoundException(Exception):
    pass


class KollaWorker(object):

    def __init__(self):
        self.base_dir = os.path.abspath(file_utils.find_base_dir())
        self.config_dir = os.path.join(self.base_dir, 'config')
        LOG.debug("Kolla-Mesos base directory: " + self.base_dir)
        self.required_vars = {}
        self.marathon_client = marathon.Client()
        self.chronos_client = chronos.Client()

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = time.time()
        ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='kolla-' + ts)
        LOG.debug('Created output dir: {}'.format(self.temp_dir))

    def get_projects(self):
        projects = set(getattr(CONF.profiles, CONF.kolla.profile))
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

        # all.yml file uses some its variables to template itself by jinja2,
        # so its raw content is used to template the file
        all_yml_name = os.path.join(self.config_dir, 'all.yml')
        with open(all_yml_name) as af:
            raw_vars = yaml.load(af)
        temp_vars = copy.deepcopy(global_vars)
        temp_vars.update(raw_vars)
        jvars = yaml.load(jinja_utils.jinja_render(all_yml_name, temp_vars))

        jvars.update(global_vars)

        for proj in self.get_projects():
            proj_yml_name = os.path.join(self.config_dir, proj,
                                         'defaults', 'main.yml')
            if os.path.exists(proj_yml_name):
                proj_vars = yaml.load(jinja_utils.jinja_render(proj_yml_name,
                                                               jvars))

                jvars.update(proj_vars)
            else:
                LOG.warning('path missing %s' % proj_yml_name)

        # override node_config_directory to empty
        jvars.update({'node_config_directory': ''})
        return jvars

    def merge_ini_files(self, source_files):
        config_p = configparser.ConfigParser()
        for src_file in source_files:
            if not src_file.startswith('/'):
                src_file = os.path.join(self.base_dir, src_file)
            if not os.path.exists(src_file):
                LOG.warning('path missing %s' % src_file)
                continue
            config_p.read(src_file)
        merged_f = cStringIO()
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

        # At first write global tools to ZK. FIXME: Make it a common profile
        conf_path = os.path.join(self.config_dir, 'common',
                                 'common_config.yml.j2')
        common_cfg = yaml.load(jinja_utils.jinja_render(conf_path, jinja_vars))
        common_node = os.path.join('kolla', 'common')
        for script in common_cfg:
            script_node = os.path.join(common_node, script)
            zk.ensure_path(script_node)
            source_path = common_cfg[script]['source']

            if not source_path.startswith('/'):
                src_file = file_utils.find_file(source_path)
            with open(src_file) as fp:
                content = fp.read()
            zk.set(script_node, content)

        # Now write services configs
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
                            src_file = file_utils.find_file(src_file)
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

                # 3. Add startup config
                start_conf = os.path.join(self.config_dir,
                                          'common/kolla-start-config.json')
                # override container_config_directory
                cont_conf_dir = 'zk://%s' % (
                    CONF.zookeeper.host)
                jinja_vars['container_config_directory'] = cont_conf_dir
                kolla_config = jinja_utils.jinja_render(start_conf, jinja_vars)
                kolla_config = kolla_config.replace('"', '\\"').replace(
                    '\n', '')

                # 4. parse the marathon app file and add the KOLLA_CONFIG
                values = {
                    'kolla_config': kolla_config,
                    'zookeeper_hosts': CONF.zookeeper.host,
                    'private_interface': CONF.network.private_interface,
                    'public_interface': CONF.network.public_interface,
                }
                for app_type in ['marathon', 'chronos']:
                    app_file = os.path.join(self.base_dir,
                                            'deployment_files',
                                            proj,
                                            '%s.%s.j2' % (service, app_type))
                    if not os.path.exists(app_file):
                        LOG.debug('potentially missing file %s' % app_file)
                        continue
                    content = jinja_utils.jinja_render(app_file, jinja_vars,
                                                       extra=values)
                    dest_file = os.path.join(self.temp_dir, proj,
                                             '%s.%s' % (service, app_type))
                    file_utils.mkdir_p(os.path.dirname(dest_file))
                    with open(dest_file, 'w') as f:
                        f.write(content)

    def write_openrc(self):
        # write an openrc to the base_dir for convience.
        openrc_file = os.path.join(self.base_dir,
                                   'deployment_files',
                                   'openrc.j2')
        content = jinja_utils.jinja_render(openrc_file, self.required_vars)
        with open('openrc', 'w') as f:
            f.write(content)
        LOG.info('Written OpenStack env to "openrc"')

    def cleanup_temp_files(self):
        """Remove temp files"""
        shutil.rmtree(self.temp_dir)

    def write_to_zookeeper(self):
        with zk_utils.connection() as zk:
            zk_utils.clean(zk)

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

    def _start_marathon_app(self, app_resource):
        if CONF.update:
            LOG.info('Applications upgrade is not implemented '
                     'yet!')
        else:
            try:
                return self.marathon_client.add_app(app_resource)
            except exception.MarathonRollback as e:
                cleanup.cleanup()
                self.write_to_zookeeper()
                raise e

    def _start_chronos_job(self, job_resource):
        if CONF.update:
            LOG.info('Bootstrap tasks for upgrade are not implemented yet!')
        else:
            try:
                return self.chronos_client.add_job(job_resource)
            except exception.ChronosRollback as e:
                cleanup.cleanup()
                self.write_to_zookeeper()
                raise e

    @retrying.retry(stop_max_attempt_number=5)
    def start(self):
        # find all marathon files and run.
        # find all cronos files and run.
        for root, dirs, names in os.walk(self.temp_dir):
            for name in names:
                app_path = os.path.join(root, name)
                with open(app_path, 'r') as app_file:
                    app_resource = json.load(app_file)
                if 'marathon' in name:
                    self._start_marathon_app(app_resource)
                else:
                    self._start_chronos_job(app_resource)


def main():
    CONF(sys.argv[1:], project='kolla-mesos')
    kolla = KollaWorker()
    kolla.setup_working_dir()
    kolla.write_to_zookeeper()
    kolla.write_openrc()
    kolla.start()

    # kolla.cleanup_temp_files()


if __name__ == '__main__':
    main()
