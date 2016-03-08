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

import json
import os.path

from oslo_config import cfg
from oslo_log import log as logging
from six.moves import configparser
from six.moves import cStringIO
import yaml

from kolla_mesos import chronos
from kolla_mesos import exception
from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import utils
from kolla_mesos.common import zk_utils
from kolla_mesos import configuration as config
from kolla_mesos import marathon
from kolla_mesos import service_definition

LOG = logging.getLogger()
CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')


class File(object):
    def __init__(self, conf, name, service_name):
        self._conf = conf
        self._name = name
        self._service_name = service_name
        self.base_dir = os.path.abspath(file_utils.find_base_dir())

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

    def write_to_zookeeper(self, zk, base_node):
        dest_node = os.path.join(base_node, self._service_name,
                                 'files', self._name)
        zk.ensure_path(dest_node)
        if isinstance(self._conf['source'], list):
            content = self.merge_ini_files(self._conf['source'])
        else:
            src_file = self._conf['source']
            if not src_file.startswith('/'):
                src_file = file_utils.find_file(src_file)
            with open(src_file) as fp:
                content = fp.read()
        zk.set(dest_node, content)


class Command(object):
    def __init__(self, conf, name, service_name):
        self._conf = conf
        self._name = name
        self._service_name = service_name

    def write_to_zookeeper(self, zk, base_node):
        for fn in self._conf.get('files', []):
            fo = File(self._conf['files'][fn], fn, self._service_name)
            fo.write_to_zookeeper(zk, base_node)


class Runner(object):
    def __init__(self, conf):
        self._conf = conf
        self.base_dir = os.path.abspath(file_utils.find_base_dir())
        self.type_name = None
        self._enabled = self._conf.get('enabled', True)
        if not self._enabled:
            LOG.warn('Service %s disabled', self._conf['name'])
        self.app_file = None
        self.app_def = None

    def _list_commands(self):
        if 'service' in self._conf:
            yield 'daemon', self._conf['service']['daemon']
        for key in self._conf.get('commands', []):
            yield key, self._conf['commands'][key]

    @classmethod
    def load_from_zk(cls, zk, service_name):
        base_node = os.path.join('kolla', CONF.kolla.deployment_id)
        dest_node = os.path.join(base_node, service_name)
        try:
            conf_raw, _st = zk.get(dest_node)
        except Exception as te:
            LOG.error('%s -> %s' % (dest_node, te))
            raise exception.KollaNotFoundException(
                service_name, entity='running service definition')

        return cls(json.loads(conf_raw))

    def write_to_zookeeper(self, zk, base_node):
        if not self._enabled:
            return
        for cmd_name, cmd_conf in self._list_commands():
            cmd = Command(cmd_conf, cmd_name, self._conf['name'])
            cmd.write_to_zookeeper(zk, base_node)

        dest_node = os.path.join(base_node, self._conf['name'])
        zk.ensure_path(dest_node)
        try:
            zk.set(dest_node, json.dumps(self._conf))
        except Exception as te:
            LOG.error('%s=%s -> %s' % (dest_node, self._conf, te))

    def _apply_service_def(self, app_def):
        """Apply the specifics from the service definition."""

    def generate_deployment_files(self, kolla_config, jinja_vars,
                                  temp_dir=None):
        if not self._enabled:
            return
        _, proj, service = self._conf['name'].split('/')
        values = {
            'service_name': self._conf['name'],
            'chronos_service_id': self._conf['name'].replace('/', '-'),
            'kolla_config': kolla_config,
            'zookeeper_hosts': CONF.zookeeper.host,
            'private_interface': CONF.network.private_interface,
            'public_interface': CONF.network.public_interface,
        }

        app_file = os.path.join(self.base_dir, 'services',
                                'default.%s.j2' % self.type_name)
        content = jinja_utils.jinja_render(app_file, jinja_vars,
                                           extra=values)
        self.app_def = yaml.load(content)
        self._apply_service_def(self.app_def)
        if temp_dir is not None:
            self.app_file = os.path.join(temp_dir, proj,
                                         '%s.%s' % (service, self.type_name))
            file_utils.mkdir_p(os.path.dirname(self.app_file))
            LOG.info(self.app_file)
            with open(self.app_file, 'w') as f:
                f.write(json.dumps(self.app_def, indent=2))

    def run(self):
        pass

    def kill(self, zk=None):
        if zk:
            dest_node = os.path.join('kolla', CONF.kolla.deployment_id,
                                     self._conf['name'])
            zk.delete(dest_node, recursive=True)


class MarathonApp(Runner):
    def __init__(self, conf):
        super(MarathonApp, self).__init__(conf)
        self.type_name = 'marathon'

    def _apply_service_def(self, app_def):
        """Apply the specifics from the service definition."""

        # 1. get docker options from "container"
        dock_opts = ('image', 'network', 'portMappings',
                     'privileged', 'parameters')
        if 'container' in self._conf:
            for opt in dock_opts:
                if opt not in self._conf['container']:
                    continue
                if 'docker' not in app_def['container']:
                    app_def['container']['docker'] = {}
                app_def['container']['docker'][opt] = utils.dict_update(
                    app_def['container']['docker'].get(opt),
                    self._conf['container'][opt])

        # 2. get remaining options from "container" and place into container
        for opt in self._conf.get('container', {}):
            if opt not in dock_opts and opt != 'docker':
                app_def['container'][opt] = utils.dict_update(
                    app_def['container'].get(opt),
                    self._conf['container'][opt])

        # 3. get options from "service"
        ignore_opts = ('daemon', )
        for opt in self._conf.get('service', {}):
            if opt not in ignore_opts:
                app_def[opt] = utils.dict_update(app_def.get(opt),
                                                 self._conf['service'][opt])

    def run(self):
        marathon_client = marathon.Client()
        marathon_client.add_app(self.app_def)
        LOG.info('Marathon app "%s" is started' %
                 self.app_def['id'])

    def kill(self, zk=None):
        marathon_client = marathon.Client()
        marathon_client.remove_app(
            '/%s/%s' % (CONF.kolla.deployment_id, self._conf['name']))
        super(MarathonApp, self).kill(zk)

    @staticmethod
    def get_state(service_name, version=None):
        marathon_client = marathon.Client()
        dep_id = '/%s/' % CONF.kolla.deployment_id
        marathon_fields = ('instances', 'tasksUnhealthy', 'tasksHealthy',
                           'tasksRunning', 'tasksStaged',
                           'version', 'healthChecks')
        app = marathon_client.get_app(
            '/%s/%s' % (CONF.kolla.deployment_id, service_name),
            version=version)
        mini_app = {'service': app['id'].replace(dep_id, ''),
                    'type': 'marathon'}
        for field in marathon_fields:
            mini_app[field] = app[field]

        mini_app['image'] = app['container']['docker']['image']
        mini_app['privileged'] = app['container']['docker']['privileged']
        return mini_app

    @staticmethod
    def list_all():
        marathon_client = marathon.Client()
        apps = marathon_client.get_apps()
        sers = []
        dep_id = '/%s/' % CONF.kolla.deployment_id
        marathon_fields = ('instances', 'tasksUnhealthy', 'tasksHealthy',
                           'tasksRunning', 'tasksStaged', 'version')

        for app in apps:
            if app['id'].startswith(dep_id):
                mini_app = {'service': app['id'].replace(dep_id, ''),
                            'type': 'marathon'}
                for field in marathon_fields:
                    mini_app[field] = app[field]
                sers.append(mini_app)
        return sers

    @staticmethod
    def scale(service_name, instances, force):
        marathon_client = marathon.Client()
        marathon_client.scale_app(
            '/%s/%s' % (CONF.kolla.deployment_id, service_name),
            instances, force=force)


class ChronosTask(Runner):
    def __init__(self, conf):
        super(ChronosTask, self).__init__(conf)
        self.type_name = 'chronos'

    def _apply_service_def(self, task_def):
        """Apply the specifics from the service definition."""

        # now merge in the service definition specifics.
        task_def['container'] = utils.dict_update(
            task_def['container'], self._conf.get('container', {}))

        if self._conf.get('task') is None:
            return
        for key in self._conf['task']:
            if key is 'env':
                for env in self._conf['task']['env']:
                    self.set_env(key, self._conf['task']['env'][env],
                                 task_def['environmentVariables'])
            else:
                task_def[key] = utils.dict_update(
                    task_def[key], self._conf['task'][key])

    def set_env(self, key, value, chronos_env):
        for cenv in chronos_env:
            if cenv['name'] == key:
                cenv['value'] = value
                return
        chronos_env.append({"name": key, "value": value})

    def run(self):
        chronos_client = chronos.Client()
        chronos_client.add_job(self.app_def)
        LOG.info('Chronos job "%s" is started' %
                 self.app_def['name'])

    def kill(self, zk=None):
        chronos_client = chronos.Client()
        chronos_service_id = self._conf['name'].replace('/', '-')
        chronos_client.remove_job(
            '%s-%s' % (CONF.kolla.deployment_id, chronos_service_id))
        super(ChronosTask, self).kill(zk)

    @staticmethod
    def get_state(service_name, version=None):
        client = chronos.Client()
        dep_id = '%s-' % CONF.kolla.deployment_id
        job_name = '%s-%s' % (CONF.kolla.deployment_id, service_name)
        job = client.get_job(job_name)
        mini_job = {'service': job['name'].replace(dep_id, ''),
                    'type': 'chronos'}
        mini_job['tasksHealthy'] = job['successCount']
        mini_job['tasksUnhealthy'] = job['errorCount']
        mini_job['tasksStaged'] = 'TODO'
        mini_job['version'] = 'N/A'
        mini_job['instances'] = 0 if job['disabled'] else 1
        mini_job['tasksRunning'] = 'TODO'
        mini_job['image'] = job['container']['image']
        return mini_job

    @staticmethod
    def list_all():
        client = chronos.Client()
        dep_id = '%s-' % CONF.kolla.deployment_id
        jobs = []
        for job in client.get_jobs():
            if job['name'].startswith(dep_id):
                mini_job = {'service': job['name'].replace(dep_id, ''),
                            'type': 'chronos'}
                mini_job['tasksHealthy'] = job['successCount']
                mini_job['tasksUnhealthy'] = job['errorCount']
                mini_job['tasksStaged'] = 'TODO'
                mini_job['version'] = 'N/A'
                mini_job['instances'] = 0 if job['disabled'] else 1
                mini_job['tasksRunning'] = 'TODO'
                jobs.append(mini_job)
        return jobs


def _load_variables(service_dir, project_name):
    config_dir = os.path.join(service_dir, '..', 'config')
    with open(file_utils.find_config_file('passwords.yml'), 'r') as gf:
        global_vars = yaml.load(gf)
    with open(file_utils.find_config_file('globals.yml'), 'r') as gf:
        global_vars.update(yaml.load(gf))
    # all.yml file uses some its variables to template itself by jinja2,
    # so its raw content is used to template the file
    all_yml_name = os.path.join(config_dir, 'all.yml')
    with open(all_yml_name) as af:
        raw_vars = yaml.load(af)
    raw_vars.update(global_vars)
    jvars = yaml.load(jinja_utils.jinja_render(all_yml_name, raw_vars))
    jvars.update(global_vars)

    proj_yml_name = os.path.join(config_dir, project_name,
                                 'defaults', 'main.yml')
    if os.path.exists(proj_yml_name):
        proj_vars = yaml.load(jinja_utils.jinja_render(proj_yml_name,
                                                       jvars))
        jvars.update(proj_vars)
    else:
        LOG.warning('Path missing %s' % proj_yml_name)
    # Add deployment_id
    jvars.update({'deployment_id': CONF.kolla.deployment_id})
    # override node_config_directory to empty
    jvars.update({'node_config_directory': ''})

    return jvars


def _load_runner(service_file, variables):
    conf = yaml.load(jinja_utils.jinja_render(service_file, variables))
    if 'service' in conf:
        runner = MarathonApp(conf)
    else:
        runner = ChronosTask(conf)
    return runner


def run_service(service_name, service_dir, variables=None):
    config_dir = os.path.join(service_dir, '..', 'config')
    base_node = os.path.join('kolla', CONF.kolla.deployment_id)
    filename = service_definition.find_service_file(service_name,
                                                    service_dir)
    if variables is None:
        proj_name = filename.split('/')[-2]
        variables = _load_variables(service_dir, proj_name)

    # 1. validate the definition with the given variables
    service_definition.validate(service_name, service_dir, variables)
    runner = _load_runner(filename, variables)
    with zk_utils.connection() as zk:
        # 2. write variables to zk (globally)
        config.write_variables_zookeeper(zk, variables)

        # 3. write common config and start script
        config.write_common_config_to_zookeeper(config_dir, zk, variables)

        # 4. write files/config to zk
        runner.write_to_zookeeper(zk, base_node)

    # 5. generate the deployment files
    kolla_config = config.get_start_config(config_dir, variables)
    runner.generate_deployment_files(kolla_config, variables)

    # 6. post deployment files to marathon/chronos
    runner.run()


def kill_service(service_name):
    with zk_utils.connection() as zk:
        if '/' not in service_name:
            # chronos job name
            service_name = service_name.replace('-', '/')
            runner = ChronosTask.load_from_zk(zk, service_name)
        else:
            runner = MarathonApp.load_from_zk(zk, service_name)

        runner.kill(zk)


def list_services():
    return ChronosTask.list_all() + MarathonApp.list_all()


def get_service(service_name, version=None):
    if '/' in service_name:
        state = MarathonApp.get_state(service_name, version)
    else:
        state = ChronosTask.get_state(service_name, version)
    return state


def get_service_logs(service_name):
    pass


def scale_service(service_name, instances, force=False):
    if '/' not in service_name:
        raise TypeError("can not scale a chronos task")

    MarathonApp.scale(service_name, instances, force)
