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

signal.signal(signal.SIGINT, signal.SIG_DFL)

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('profiles', 'kolla_mesos.config.profiles')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')
CONF.import_opt('update', 'kolla_mesos.config.deploy_cli')
CONF.import_opt('force', 'kolla_mesos.config.deploy_cli')
CONF.import_opt('debug', 'kolla_mesos.config.deploy_cli')


class KollaDirNotFoundException(Exception):
    pass


class KollaWorker(object):

    def __init__(self):
        self.init_logger()
        self.base_dir = os.path.abspath(file_utils.find_base_dir())
        self.config_dir = os.path.join(self.base_dir, 'config')
        self.LOG.debug("Kolla-Mesos base directory: %s" % self.base_dir)
        self.required_vars = {}
        self.marathon_client = marathon.Client()
        self.chronos_client = chronos.Client()
        self.start_time = time.time()

    def init_logger(self):
        stdout_handler = logging.StreamHandler(sys.stdout)
        log_format = logging.Formatter('%(levelname)s - %(message)s')
        stdout_handler.setFormatter(log_format)
        LOG = logging.getLogger(__name__)
        loglevel = logging.DEBUG if CONF.debug else logging.INFO
        LOG.setLevel(loglevel)
        LOG.addHandler(stdout_handler)
        self.LOG = LOG

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = datetime.datetime.fromtimestamp(
            self.start_time
        ).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='kolla-' + ts)
        self.LOG.debug('Created output dir: %s' % self.temp_dir)

    def get_projects(self):
        projects = set(getattr(CONF.profiles, CONF.kolla.profile))
        self.LOG.debug('Projects are: %s' % projects)
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
        raw_vars.update(global_vars)
        jvars = yaml.load(jinja_utils.jinja_render(all_yml_name, raw_vars))

        jvars.update(global_vars)

        for proj in self.get_projects():
            proj_yml_name = os.path.join(self.config_dir, proj,
                                         'defaults', 'main.yml')
            if os.path.exists(proj_yml_name):
                proj_vars = yaml.load(jinja_utils.jinja_render(proj_yml_name,
                                                               jvars))

                jvars.update(proj_vars)
            else:
                self.LOG.warning('Path missing %s' % proj_yml_name)

        # Add deployment_id
        jvars.update({'deployment_id': self.deployment_id})
        # override node_config_directory to empty
        jvars.update({'node_config_directory': ''})
        return jvars

    def merge_ini_files(self, source_files):
        config_p = configparser.ConfigParser()
        for src_file in source_files:
            if not src_file.startswith('/'):
                src_file = os.path.join(self.base_dir, src_file)
            if not os.path.exists(src_file):
                self.LOG.warning('Path missing %s' % src_file)
                continue
            config_p.read(src_file)
        merged_f = cStringIO()
        config_p.write(merged_f)
        return merged_f.getvalue()

    def gen_deployment_id(self):

        if CONF.kolla.deployment_id_prefix and CONF.kolla.deployment_id:
            self.LOG.info('You can\'t use "deployment-id" and '
                          '"deployment-id-prefix" together. Choose one.')
            sys.exit(1)

        uniq_name = CONF.kolla.deployment_id is not None
        deploy_prefix = CONF.kolla.deployment_id_prefix is not None

        if uniq_name:
            self.deployment_id = CONF.kolla.deployment_id
        else:
            ts = datetime.datetime.fromtimestamp(
                self.start_time
            ).strftime('%Y-%m-%d-%H-%M-%S')
            deployment_id = (CONF.kolla.deployment_id_prefix + '-' + ts
                             if deploy_prefix else ts)
            self.deployment_id = deployment_id
        self.LOG.info('Deployment ID: %s' % self.deployment_id)

    def write_config_to_zookeeper(self, zk):
        jinja_vars = self.get_jinja_vars()
        self.LOG.debug('Jinja_vars is: %s' % jinja_vars)
        self.required_vars = jinja_vars

        for var in jinja_vars:
            if not jinja_vars[var]:
                self.LOG.info('Cant find var "%s" in jinja_vars' % var)
            if 'image' in var:
                self.LOG.debug('%s is "%s"' % (var, jinja_vars[var]))

        # At first write global tools to ZK. FIXME: Make it a common profile
        conf_path = os.path.join(self.config_dir, 'common',
                                 'common_config.yml.j2')
        common_cfg = yaml.load(jinja_utils.jinja_render(conf_path, jinja_vars))
        common_node = os.path.join('kolla', 'common')
        for script in common_cfg:
            script_node = os.path.join(common_node, script)
            zk.ensure_path(script_node)
            source_path = common_cfg[script]['source']

            src_file = source_path
            if not source_path.startswith('/'):
                src_file = file_utils.find_file(source_path)
            with open(src_file) as fp:
                content = fp.read()
            zk.set(script_node, content)

        # Now write services configs
        for proj in self.get_projects():
            self.LOG.debug('Current project is %s' % proj)
            proj_dir = os.path.join(self.config_dir, proj)
            if not os.path.exists(proj_dir):
                self.LOG.info('Cant find project dir "%s"' % proj_dir)
                continue

            conf_path = os.path.join(self.config_dir, proj,
                                     '%s_config.yml.j2' % proj)
            extra = yaml.load(jinja_utils.jinja_render(conf_path, jinja_vars))

            base_node = os.path.join('kolla', self.deployment_id)
            # TODO() should be proj, service, not proj, proj
            dest_node = os.path.join(base_node, 'config', proj, proj)
            zk.ensure_path(dest_node)
            zk.set(dest_node, json.dumps(extra))
            self.LOG.debug('Created "%s" node in zookeeper' % dest_node)

            for service in extra['config'][proj]:
                self.LOG.debug('Current service is %s' % service)
                # write the config files
                for name, item in extra['config'][proj][service].iteritems():
                    dest_node = os.path.join(base_node, 'config', proj,
                                             service, name)
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
                    self.LOG.debug('Created "%s" node in zookeeper' %
                                   dest_node)

                # write the commands
                for name, item in extra['commands'][proj][service].iteritems():
                    dest_node = os.path.join(base_node, 'commands', proj,
                                             service, name)
                    zk.ensure_path(dest_node)
                    try:
                        zk.set(dest_node, json.dumps(item))
                        self.LOG.debug('Created "%s" node in zookeeper' %
                                       dest_node)
                    except Exception as te:
                        self.LOG.error('Cant create "%s" node with "%s" item'
                                       ' in Zookeeper. Error was: "%s"' %
                                       (dest_node, item, te))

                # 3. Add startup config
                start_conf = os.path.join(self.config_dir,
                                          'common/kolla-start-config.json')
                # override container_config_directory
                cont_conf_dir = 'zk://%s' % (CONF.zookeeper.host)
                jinja_vars['container_config_directory'] = cont_conf_dir
                jinja_vars['deployment_id'] = self.deployment_id
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
                        self.LOG.debug('Potentially missing file %s' %
                                       app_file)
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
        self.LOG.info('Written OpenStack env to "openrc"')

    def cleanup_temp_files(self):
        """Remove temp files"""
        shutil.rmtree(self.temp_dir)
        self.LOG.debug('Tmp file %s removed' % self.temp_dir)

    def write_to_zookeeper(self):
        with zk_utils.connection() as zk:

            base_node = os.path.join('kolla', self.deployment_id)
            if zk.exists(base_node) and CONF.force:
                self.LOG.info('Deleting "%s" ZK node tree' % base_node)
                zk.delete(base_node, recursive=True)
            elif zk.exists(base_node) and not CONF.force:
                self.LOG.info('"%s" ZK node tree is already exists. If you'
                              ' want to delete it, use --force' % base_node)
                sys.exit(1)

            self.write_config_to_zookeeper(zk)

            filter_out = ['groups', 'hostvars', 'kolla_config',
                          'inventory_hostname']
            for var in self.required_vars:
                if (var in filter_out):
                    self.LOG.debug('Var "%s" with value "%s" is filtered out' %
                                   (var, self.required_vars[var]))
                    continue
                var_value = self.required_vars[var]
                if isinstance(self.required_vars[var], dict):
                    var_value = json.dumps(self.required_vars[var])
                var_path = os.path.join(base_node, 'variables', var)
                zk.ensure_path(var_path)
                try:
                    zk.set(var_path, var_value)
                    self.LOG.debug('Updated "%s" node in zookeeper.' %
                                   var_path)
                except Exception as te:
                    self.LOG.error('Cant create "%s" node with "%s" item in '
                                   'Zookeeper. Error was: "%s"' %
                                   (var_path, var_value, te))

    def _start_marathon_app(self, app_resource):
        if CONF.update:
            self.LOG.info('Applications upgrade is not implemented yet!')
        else:
            try:
                return self.marathon_client.add_app(app_resource)
            except exception.MarathonRollback as e:
                cleanup.cleanup()
                self.write_to_zookeeper()
                raise e

    def _start_chronos_job(self, job_resource):
        if CONF.update:
            self.LOG.info('Bootstrap tasks for upgrade are not implemented'
                          ' yet!')
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
                    deployment_id = {'KOLLA_DEPLOYMENT_ID': self.deployment_id}
                    app_resource['env'].update(deployment_id)
                    self._start_marathon_app(app_resource)
                    self.LOG.info('Marathon app "%s" is started' %
                                  app_resource['id'])
                else:
                    deployment_id = {'name': 'KOLLA_DEPLOYMENT_ID',
                                     'value': self.deployment_id}
                    app_resource['environmentVariables'].append(deployment_id)
                    self._start_chronos_job(app_resource)
                    self.LOG.info('Chronos job "%s" is started' %
                                  app_resource['name'])

    def print_summary(self):
        self.LOG.info('=' * 80)
        self.LOG.info('Openstack deployed, check urls below for more info.')
        self.LOG.info('Marathon: %s', CONF.marathon.host)
        self.LOG.info('Mesos: %s', CONF.marathon.host.replace('8080', '5050'))
        self.LOG.info('Chronos: %s', CONF.chronos.host)


def main():
    CONF(sys.argv[1:], project='kolla-mesos')
    kolla = KollaWorker()
    kolla.setup_working_dir()
    kolla.gen_deployment_id()
    kolla.write_to_zookeeper()
    kolla.write_openrc()
    kolla.start()
    kolla.print_summary()
    # kolla.cleanup_temp_files()


if __name__ == '__main__':
    main()
