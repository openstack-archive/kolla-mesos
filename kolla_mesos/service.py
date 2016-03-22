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

import functools
import itertools
import json
import os.path
import time

from kazoo import exceptions
from oslo_config import cfg
from oslo_log import log as logging
from six.moves import configparser
from six.moves import cStringIO
import yaml

from kolla_mesos import chronos
from kolla_mesos.common import file_utils
from kolla_mesos.common import jinja_utils
from kolla_mesos.common import utils
from kolla_mesos.common import zk_utils
from kolla_mesos import configuration as config
from kolla_mesos import exception
from kolla_mesos import marathon
from kolla_mesos import mesos
from kolla_mesos import service_definition

LOG = logging.getLogger()
CONF = cfg.CONF
CONF.import_group('kolla', 'kolla_mesos.config.kolla')
CONF.import_group('zookeeper', 'kolla_mesos.config.zookeeper')
CONF.import_group('marathon', 'kolla_mesos.config.marathon')
CONF.import_group('chronos', 'kolla_mesos.config.chronos')


def execute_if_enabled(f):
    """Decorator for executing methods only if runner is enabled."""
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        if not self._enabled:
            return
        return f(self, *args, **kwargs)
    return wrapper


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
        zk.set(dest_node, content.encode('utf-8'))


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

    def __new__(cls, conf):
        """Create a new Runner of the appropriate class for its type."""
        if cls != Runner:
            # Call is already for a subclass, so pass it through
            RunnerClass = cls
        else:
            if 'service' in conf and 'task' not in conf:
                RunnerClass = MarathonApp
            else:
                RunnerClass = ChronosTask
        return super(Runner, cls).__new__(RunnerClass)

    @classmethod
    def load_from_zk(cls, zk, service_name):
        variables = _load_variables_from_zk(zk)
        base_node = os.path.join('kolla', CONF.kolla.deployment_id)
        if '/' not in service_name:
            service_name = service_name.replace('-', '/')
        dest_node = os.path.join(base_node, service_name)
        try:
            conf_raw, _st = zk.get(dest_node)
        except Exception as te:
            LOG.error('%s -> %s' % (dest_node, te))
            raise exception.KollaNotFoundException(
                service_name, entity='running service definition')
        return Runner(yaml.load(
                      jinja_utils.jinja_render_str(conf_raw.decode('utf-8'),
                                                   variables)))

    @classmethod
    def load_from_file(cls, service_file, variables):
        return Runner(yaml.load(
                      jinja_utils.jinja_render(service_file, variables)))

    def _list_commands(self):
        if 'service' in self._conf:
            yield 'daemon', self._conf['service']['daemon']
        for key in self._conf.get('commands', []):
            yield key, self._conf['commands'][key]

    @execute_if_enabled
    def write_to_zookeeper(self, zk, base_node):
        for cmd_name, cmd_conf in self._list_commands():
            cmd = Command(cmd_conf, cmd_name, self._conf['name'])
            cmd.write_to_zookeeper(zk, base_node)

        dest_node = os.path.join(base_node, self._conf['name'])
        zk.ensure_path(dest_node)
        try:
            zk.set(dest_node, json.dumps(self._conf).encode('utf-8'))
        except Exception as te:
            LOG.error('%s=%s -> %s' % (dest_node, self._conf, te))

    def _apply_service_def(self, app_def):
        """Apply the specifics from the service definition."""

    @execute_if_enabled
    def generate_deployment_files(self, kolla_config, jinja_vars,
                                  temp_dir=None):
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

    def get_live_deployment_file(self):
        """Get the current version of the deployment from Marathon."""
        raise exception.KollaNotSupportedException(
            operation='get_live_deployment_file', entity=self.type_name)

    def run(self):
        raise exception.KollaNotSupportedException(operation='run',
                                                   entity=self.type_name)

    def update(self):
        raise exception.KollaNotSupportedException(operation='update',
                                                   entity=self.type_name)

    def scale(self, instances, force=False):
        raise exception.KollaNotSupportedException(operation='scale',
                                                   entity=self.type_name)

    def snapshot(self, zk, output_dir, variables):
        """Produce the required files to revert the service.

        The files should have the same basic structure as the original
        service definition:
        <output_dir>/<project>/<service>.yml.j2
        <output_dir>/<project>/templates/*
        <output_dir>/<project>/<service>.{marathon|chronos}
        <output_dir>/variables.yml
        """

        service_name = self._conf['name'].split('/')[-1]
        proj = self._conf['name'].split('/')[-2]
        proj_dir = os.path.join(output_dir, proj)
        file_utils.mkdir_p(proj_dir)

        # variables
        # Note: if this exists, then the variables will be merged.
        var_path = os.path.join(output_dir, 'variables.yml')
        if os.path.exists(var_path):
            with open(var_path) as vfp:
                global_vars = yaml.load(vfp)
                LOG.info('global_vars: %s', yaml.dump(global_vars))
                global_vars.update(variables)
        else:
            global_vars = variables

        with open(var_path, 'w') as vfp:
            vfp.write(yaml.dump(global_vars, default_flow_style=False))

        # service definition and files
        with open(os.path.join(proj_dir, '%s.yml.j2' % service_name),
                  'w') as sfp:
            sfp.write(json.dumps(self._conf))

        # get and write the files
        files_node = os.path.join('kolla', CONF.kolla.deployment_id,
                                  self._conf['name'], 'files')
        if zk.exists(files_node):
            file_utils.mkdir_p(os.path.join(proj_dir, 'templates'))
            try:
                files = zk.get_children(files_node)
            except exceptions.NoNodeError:
                files = []
            for fn in files:
                with open(os.path.join(proj_dir, 'templates', fn), 'w') as fp:
                    content, _st = zk.get(os.path.join(files_node, fn))
                    fp.write(content)

        # deployment file
        self.app_file = os.path.join(proj_dir, '%s.%s' % (service_name,
                                                          self.type_name))
        self.app_def = self.get_live_deployment_file()
        with open(self.app_file, 'w') as dfp:
            dfp.write(json.dumps(self.app_def, indent=2))

    def kill(self, zk=None):
        if zk:
            dest_node = os.path.join('kolla', CONF.kolla.deployment_id,
                                     self._conf['name'])
            zk.delete(dest_node, recursive=True)


class MarathonApp(Runner):
    def __init__(self, conf):
        super(MarathonApp, self).__init__(conf)
        self.type_name = 'marathon'
        self._marathon_client = None

    def _client(self):
        if self._marathon_client is None:
            self._marathon_client = marathon.Client()
        return self._marathon_client

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

    @execute_if_enabled
    def run(self):
        self._client().add_app(self.app_def)
        LOG.info('Marathon app "%s" is started' %
                 self.app_def['id'])

    def update(self):
        self._client().update_job(self._get_app_id(), self.app_def)

    def _get_app_id(self):
        return '/%s/%s' % (CONF.kolla.deployment_id, self._conf['name'])

    def kill(self, zk=None):
        self._client().remove_app(self._get_app_id())
        super(MarathonApp, self).kill(zk)

    def get_live_deployment_file(self):
        """Get the current version of the deployment from Marathon."""
        return self._client().get_app(self._get_app_id())

    def scale(self, instances, force=False):
        self._client().scale_app(self._get_app_id(),
                                 instances, force=force)

    @staticmethod
    def _get_common_fields(app):
        dep_id = '/%s/' % CONF.kolla.deployment_id
        marathon_fields = ('instances', 'tasksUnhealthy', 'tasksHealthy',
                           'tasksRunning', 'tasksStaged',
                           'version', 'healthChecks')
        mini_app = dict((field, app[field]) for field in marathon_fields)
        mini_app.update({'service': app['id'].replace(dep_id, ''),
                         'type': 'marathon'})
        return mini_app

    def get_state(self, version=None):
        app = self._client().get_app(self._get_app_id(), version=version)
        mini_app = MarathonApp._get_common_fields(app)
        mini_app['image'] = app['container']['docker']['image']
        mini_app['privileged'] = app['container']['docker']['privileged']
        return mini_app

    @staticmethod
    def list_all():
        dep_id = '/%s/' % CONF.kolla.deployment_id
        marathon_client = marathon.Client()
        apps = marathon_client.get_apps()
        return [MarathonApp._get_common_fields(app) for app in apps
                if app['id'].startswith(dep_id)]


class ChronosTask(Runner):
    def __init__(self, conf):
        super(ChronosTask, self).__init__(conf)
        self.type_name = 'chronos'
        self._chronos_client = None

    def _client(self):
        if self._chronos_client is None:
            self._chronos_client = chronos.Client()
        return self._chronos_client

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

    @execute_if_enabled
    def run(self):
        self._client().add_job(self.app_def)
        LOG.info('Chronos job "%s" is started' %
                 self.app_def['name'])

    def _get_job_name(self):
        return '%s-%s' % (CONF.kolla.deployment_id,
                          self._conf['name'].replace('/', '-'))

    def update(self):
        self._client().update_job(self._get_job_name(), self.app_def)

    def kill(self, zk=None):
        self._client().remove_job(self._get_job_name())
        super(ChronosTask, self).kill(zk)

    @staticmethod
    def _job_to_public_format(job):
        dep_id = '%s-' % CONF.kolla.deployment_id
        mini_job = {'service': job['name'].replace(dep_id, ''),
                    'type': 'chronos'}
        mini_job['tasksHealthy'] = job['successCount']
        mini_job['tasksUnhealthy'] = job['errorCount']
        mini_job['instances'] = 0 if job['disabled'] else 1
        mini_job['version'] = job['lastSuccess']
        mini_job['tasksStaged'] = 'N/A'
        mini_job['tasksRunning'] = 'N/A'
        return mini_job

    def get_state(self, version=None):
        job = self._client().get_job(self._get_job_name())
        mini_job = ChronosTask._job_to_public_format(job)
        mini_job['image'] = job['container']['image']
        return mini_job

    @staticmethod
    def list_all():
        client = chronos.Client()
        dep_id = '%s-' % CONF.kolla.deployment_id
        jobs = []
        for job in client.get_jobs():
            if job['name'].startswith(dep_id):
                jobs.append(ChronosTask._job_to_public_format(job))
        return jobs


def _load_variables_from_zk(zk):
    path = os.path.join('/kolla', CONF.kolla.deployment_id, 'variables')
    variables = {}
    try:
        var_names = zk.get_children(path)
    except exceptions.NoNodeError:
        var_names = []
    for var in var_names:
        value, _stat = zk.get(os.path.join(path, var))
        variables[var] = value.decode('utf-8')
    # Add deployment_id
    variables.update({'deployment_id': CONF.kolla.deployment_id})
    # override node_config_directory to empty
    variables.update({'node_config_directory': ''})
    return variables


class JvarsDict(dict):
    """Dict which can contain the 'global_vars' which are always preserved.

    They cannot be be overriden by any update nor single item setting.
    """

    def __init__(self, *args, **kwargs):
        super(JvarsDict, self).__init__(*args, **kwargs)
        self.global_vars = {}

    def __setitem__(self, key, value):
        if key in self.global_vars:
            return
        return super(JvarsDict, self).__setitem__(key, value)

    def update(self, other_dict):
        filtered_dict = {key: value for key, value in other_dict.items()
                         if key not in self.global_vars}
        super(JvarsDict, self).update(filtered_dict)

    def set_global_vars(self, global_vars):
        self.update(global_vars)
        self.global_vars = global_vars


def _load_variables_from_file(service_dir, project_name):
    config_dir = os.path.join(service_dir, '..', 'config')
    jvars = JvarsDict()
    with open(file_utils.find_config_file('globals.yml'), 'r') as gf:
        jvars.set_global_vars(yaml.load(gf))
    with open(file_utils.find_config_file('passwords.yml'), 'r') as gf:
        jvars.update(yaml.load(gf))
    # Apply the basic variables that aren't defined in any config file.
    jvars.update({
        'deployment_id': CONF.kolla.deployment_id,
        'node_config_directory': '',
        'timestamp': str(time.time())
    })
    # Get the exact marathon framework name.
    config.get_marathon_framework(jvars)
    # all.yml file uses some its variables to template itself by jinja2,
    # so its raw content is used to template the file
    all_yml_name = os.path.join(config_dir, 'all.yml')
    jinja_utils.yaml_jinja_render(all_yml_name, jvars)
    # Apply the dynamic deployment variables.
    config.apply_deployment_vars(jvars)

    proj_yml_name = os.path.join(config_dir, project_name,
                                 'defaults', 'main.yml')
    if os.path.exists(proj_yml_name):
        jinja_utils.yaml_jinja_render(proj_yml_name, jvars)
    else:
        LOG.warning('Path missing %s' % proj_yml_name)
    return jvars


def _load_variables_from_snapshot(service_dir):
    var_path = os.path.join(service_dir, 'variables.yml')
    with open(var_path) as vfp:
        return yaml.load(vfp)


def _build_runner(service_name, service_dir, variables=None):
    config_dir = os.path.join(service_dir, '..', 'config')
    base_node = os.path.join('kolla', CONF.kolla.deployment_id)
    filename = service_definition.find_service_file(service_name,
                                                    service_dir)
    proj_name = filename.split('/')[-2]
    proj_yml_name = os.path.join(config_dir, proj_name,
                                 'defaults', 'main.yml')

    # is this a snapshot or from original src?
    var_path = os.path.join(service_dir, 'variables.yml')
    is_snapshot = (os.path.exists(var_path) and
                   not os.path.exists(proj_yml_name))

    if variables is None:
        if not is_snapshot:
            variables = _load_variables_from_file(service_dir, proj_name)
        else:
            variables = _load_variables_from_snapshot(service_dir)

    # 1. validate the definition with the given variables
    service_definition.validate(service_name, service_dir, variables)
    runner = Runner.load_from_file(filename, variables)
    with zk_utils.connection() as zk:
        # 2. write variables to zk (globally)
        config.write_variables_zookeeper(zk, variables,
                                         overwrite=not is_snapshot)
        # 3. write common config and start script
        config.write_common_config_to_zookeeper(config_dir, zk, variables,
                                                overwrite=not is_snapshot)

        # 4. write files/config to zk
        runner.write_to_zookeeper(zk, base_node)

    # 5. generate the deployment files
    kolla_config = config.get_start_config(config_dir, variables)
    runner.generate_deployment_files(kolla_config, variables)
    return runner


# Public API below
##################

def run_service(service_name, service_dir, variables=None):
    runner = _build_runner(service_name, service_dir, variables=variables)
    runner.run()


def update_service(service_name, service_dir, variables=None):
    runner = _build_runner(service_name, service_dir, variables=variables)
    runner.update()


def kill_service(service_name):
    with zk_utils.connection() as zk:
        runner = Runner.load_from_zk(zk, service_name)
        runner.kill(zk)


def snapshot_service(service_name, output_dir):
    with zk_utils.connection() as zk:
        runner = Runner.load_from_zk(zk, service_name)
        variables = _load_variables_from_zk(zk)
        runner.snapshot(zk, output_dir, variables)


def get_service(service_name, version=None):
    with zk_utils.connection() as zk:
        runner = Runner.load_from_zk(zk, service_name)
        return runner.get_state(version)


def scale_service(service_name, instances, force=False):
    with zk_utils.connection() as zk:
        runner = Runner.load_from_zk(zk, service_name)
        return runner.scale(instances, force)


def list_services():
    return ChronosTask.list_all() + MarathonApp.list_all()


def get_service_logs(service_name, file_name):
    slave_id = None
    mesos_client = mesos.Client()
    master_state = mesos_client.get_state()

    if '/' in service_name:
        task_name = '%s/%s' % (
            CONF.kolla.deployment_id, service_name)
        task_name = task_name.replace('/', '_')
    else:
        task_name = '%s-%s' % (CONF.kolla.deployment_id, service_name)

    for framework in itertools.chain(
            master_state['frameworks'],
            master_state['completed_frameworks']):
        if not slave_id:
            for task in itertools.chain(
                    framework['tasks'], framework['completed_tasks']):
                if task_name in task['id']:
                    slave_id = task['slave_id']
                    break

    if not slave_id:
        raise exception.KollaNotFoundException(
            service_name, 'Mesos slave for the service')

    slave_pid = None
    for slave in master_state['slaves']:
        if slave_id == slave['id']:
            slave_pid = slave['pid']
            break

    slave_state = mesos_client.get_slave_state(slave_pid)
    executor_dir = None
    for framework in itertools.chain(
            slave_state['completed_frameworks'], slave_state['frameworks']):
        for executor in itertools.chain(
                framework['completed_executors'], framework['executors']):
            if task_name in executor['id']:
                executor_dir = executor['directory']

    if not executor_dir:
        raise exception.KollaNotFoundException(
            service_name, 'executor for the service')

    file_path = os.path.join(executor_dir, file_name)
    return mesos_client.read_file(file_path, slave_pid)
