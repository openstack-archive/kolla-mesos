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
import os
import signal
import sys
import tempfile
import time

from oslo_config import cfg
from oslo_log import log as logging
import retrying
import shutil
import yaml

from kolla_mesos import chronos
from kolla_mesos import cleanup
from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import mesos_utils
from kolla_mesos.common import yaml_utils
from kolla_mesos.common import zk_utils
from kolla_mesos import configuration
from kolla_mesos import exception
from kolla_mesos import marathon
from kolla_mesos import service

signal.signal(signal.SIGINT, signal.SIG_DFL)

CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('profiles', 'kolla_mesos.config.profiles')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')
CONF.import_opt('update', 'kolla_mesos.config.deploy_cli')
CONF.import_opt('force', 'kolla_mesos.config.deploy_cli')

LOG = logging.getLogger()
logging.register_options(CONF)


class KollaWorker(object):

    def __init__(self):
        self.base_dir = os.path.abspath(file_utils.find_base_dir())
        self.config_dir = os.path.join(self.base_dir, 'config')
        LOG.debug("Kolla-Mesos base directory: %s" % self.base_dir)
        self.required_vars = {}
        self.marathon_client = marathon.Client()
        self.chronos_client = chronos.Client()
        self.start_time = time.time()

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = datetime.datetime.fromtimestamp(
            self.start_time
        ).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='kolla-' + ts)
        LOG.debug('Created output dir: %s' % self.temp_dir)

    def get_projects(self):
        projects = set(getattr(CONF.profiles, CONF.kolla.profile))
        LOG.debug('Projects are: %s' % projects)
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
                LOG.warning('Path missing %s' % proj_yml_name)

        jvars.update({
            'deployment_id': self.deployment_id,
            'node_config_directory': ''
        })
        if yaml_utils.str_to_bool(jvars['autodetect_resources']):
            controller_nodes, compute_nodes, storage_nodes, all_nodes = \
                mesos_utils.get_number_of_nodes()
        else:
            controller_nodes = jvars.get('controller_nodes') or 1
            compute_nodes = jvars.get('compute_nodes') or 1
            storage_nodes = jvars.get('storage_nodes') or 1
            all_nodes = controller_nodes + compute_nodes + storage_nodes
        jvars.update({
            'controller_nodes': str(controller_nodes),
            'compute_nodes': str(compute_nodes),
            'storage_nodes': str(storage_nodes),
            'all_nodes': str(all_nodes)
        })
        return jvars

    def gen_deployment_id(self):

        if CONF.kolla.deployment_id_prefix and CONF.kolla.deployment_id:
            LOG.info('You can\'t use "deployment-id" and '
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
                             if deploy_prefix else 'kolla')
            self.deployment_id = deployment_id
        LOG.info('Deployment ID: %s' % self.deployment_id)

    def process_service_config(self, zk, proj, conf_path,
                               jinja_vars, kolla_config):
        conf = yaml.load(jinja_utils.jinja_render(conf_path, jinja_vars))
        if 'service' in conf:
            runner = service.MarathonApp(conf)
        else:
            runner = service.ChronosTask(conf)
        base_node = os.path.join('kolla', self.deployment_id)
        runner.write_to_zookeeper(zk, base_node)
        runner.generate_deployment_files(kolla_config, jinja_vars,
                                         self.temp_dir)

    def _write_common_config_to_zookeeper(self, zk, jinja_vars):
        # 1. At first write global tools to ZK. FIXME: Make it a common profile
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

        # 2. Add startup config
        start_conf = os.path.join(self.config_dir,
                                  'common/kolla-start-config.json')
        # override container_config_directory
        cont_conf_dir = 'zk://%s' % (CONF.zookeeper.host)
        jinja_vars['container_config_directory'] = cont_conf_dir
        jinja_vars['deployment_id'] = self.deployment_id
        kolla_config = jinja_utils.jinja_render(start_conf, jinja_vars)
        kolla_config = kolla_config.replace('"', '\\"').replace('\n', '')

        return kolla_config

    def write_config_to_zookeeper(self, zk):
        jinja_vars = self.get_jinja_vars()
        LOG.debug('Jinja_vars is: %s' % jinja_vars)
        self.required_vars = jinja_vars

        for var in jinja_vars:
            if jinja_vars[var] is None:
                LOG.info('jinja_vars[%s] is None' % var)
            if 'image' in var:
                LOG.debug('%s is "%s"' % (var, jinja_vars[var]))

        configuration.write_common_config_to_zookeeper(self.config_dir, zk,
                                                       jinja_vars)
        kolla_config = configuration.get_start_config(self.config_dir,
                                                      jinja_vars)

        # Now write services configs
        for proj in self.get_projects():
            conf_path = os.path.join(self.base_dir, 'services', proj)
            LOG.info('Current project is %s' % conf_path)
            for root, dirs, names in os.walk(conf_path):
                [self.process_service_config(zk, proj,
                                             os.path.join(root, name),
                                             jinja_vars, kolla_config)
                 for name in names]

    def write_openrc(self):
        # write an openrc to the base_dir for convience.
        openrc_file = os.path.join(self.base_dir, 'config', 'openrc.j2')
        content = jinja_utils.jinja_render(openrc_file, self.required_vars)
        with open('openrc', 'w') as f:
            f.write(content)
        LOG.info('Written OpenStack env to "openrc"')

    def cleanup_temp_files(self):
        """Remove temp files"""
        shutil.rmtree(self.temp_dir)
        LOG.debug('Tmp file %s removed' % self.temp_dir)

    def write_to_zookeeper(self):
        with zk_utils.connection() as zk:

            base_node = os.path.join('kolla', self.deployment_id)
            if zk.exists(base_node) and CONF.force:
                LOG.info('Deleting "%s" ZK node tree' % base_node)
                zk.delete(base_node, recursive=True)
            elif zk.exists(base_node) and not CONF.force:
                LOG.info('"%s" ZK node tree is already exists. If you'
                         ' want to delete it, use --force' % base_node)
                sys.exit(1)

            self.write_config_to_zookeeper(zk)

            filter_out = ['groups', 'hostvars', 'kolla_config',
                          'inventory_hostname']
            for var in self.required_vars:
                if (var in filter_out):
                    LOG.debug('Var "%s" with value "%s" is filtered out' %
                              (var, self.required_vars[var]))
                    continue
                var_value = self.required_vars[var]
                if isinstance(self.required_vars[var], dict):
                    var_value = json.dumps(self.required_vars[var])
                var_path = os.path.join(base_node, 'variables', var)
                zk.ensure_path(var_path)
                zk.set(var_path, "" if var_value is None else var_value)
                LOG.debug('Updated "%s" node in zookeeper.' % var_path)

    def _start_marathon_app(self, app_resource):
        if CONF.update:
            LOG.info('Applications upgrade is not implemented yet!')
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
                    deployment_id = {'KOLLA_DEPLOYMENT_ID': self.deployment_id}
                    app_resource['env'].update(deployment_id)
                    self._start_marathon_app(app_resource)
                    LOG.info('Marathon app "%s" is started' %
                             app_resource['id'])
                else:
                    deployment_id = {'name': 'KOLLA_DEPLOYMENT_ID',
                                     'value': self.deployment_id}
                    app_resource['environmentVariables'].append(deployment_id)
                    self._start_chronos_job(app_resource)
                    LOG.info('Chronos job "%s" is started' %
                             app_resource['name'])

    def print_summary(self):
        LOG.info('=' * 80)
        LOG.info('Openstack deployed, check urls below for more info.')
        LOG.info('Marathon: %s', CONF.marathon.host)
        LOG.info('Mesos: %s', CONF.marathon.host.replace('8080', '5050'))
        LOG.info('Chronos: %s', CONF.chronos.host)


def main():
    CONF(sys.argv[1:], project='kolla-mesos')
    logging.setup(CONF, 'kolla-mesos')
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
