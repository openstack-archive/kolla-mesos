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


import os.path
import yaml

import jinja2

from kolla_mesos.common import jinja_utils
from kolla_mesos import exception

CNF_FIELDS = ('source', 'dest', 'owner', 'perm')
CMD_FIELDS = ('run_once', 'dependencies', 'command', 'env',
              'delay', 'retries', 'files')


def inspect(service_name, service_dir):
    if not os.path.exists(service_dir):
        raise exception.KollaDirNotFoundException(service_dir)
    filename = os.path.join(service_dir, '%s.yml.j2' % service_name)
    try:
        required_variables = set.union(
            jinja_utils.jinja_find_required_variables(filename))
    except jinja2.exceptions.TemplateNotFound:
        raise exception.KollaFileNotFoundException(filename)
    return dict(required_variables=list(required_variables))


def validate(service_name, service_dir, variables=None, deps=None):
    if variables is None:
        variables = {}
    if deps is None:
        deps = {}

    if not os.path.exists(service_dir):
        raise exception.KollaDirNotFoundException(service_dir)

    filename = os.path.join(service_dir, '%s.yml.j2' % service_name)
    try:
        cnf = yaml.load(jinja_utils.jinja_render(filename, variables))
    except jinja2.exceptions.TemplateNotFound:
        raise exception.KollaFileNotFoundException(filename)

    def get_commands():
        for cmd in cnf.get('commands', {}):
            yield cmd, cnf['commands'][cmd]
        if 'service' in cnf:
            yield 'daemon', cnf['service']['daemon']

    _, group, role = cnf['name'].split('/')
    for cmd, cmd_info in get_commands():
        _validate_command(filename, cmd, cmd_info, deps, role, service_dir)
    return deps


def _validate_config(filename, conf, service_dir):
    for file in conf:
        for key in conf[file]:
            assert key in CNF_FIELDS, '%s: %s not in %s' % (filename,
                                                            key, CNF_FIELDS)
        srcs = conf[file]['source']
        if isinstance(srcs, str):
            srcs = [srcs]
        for src in srcs:
            file_path = os.path.join(service_dir, '..', src)
            if not file_path.startswith('/etc'):
                assert os.path.exists(file_path), '%s missing' % file_path


def _validate_command(filename, cmd, cmd_info, deps, role, service_dir):
    for key in cmd_info:
        assert key in CMD_FIELDS, '%s not in %s' % (key, CMD_FIELDS)

    reg = '%s/%s' % (role, cmd)
    reqs = cmd_info.get('dependencies', [])
    if reg not in deps:
        deps[reg] = {'waiters': {}}
    deps[reg]['registered_by'] = cmd
    deps[reg]['name'] = cmd
    deps[reg]['run_by'] = filename
    for req in reqs:
        if req not in deps:
            deps[req] = {'waiters': {}}
        deps[req]['waiters'][cmd] = reg
    if 'files' in cmd_info:
        _validate_config(filename, cmd_info['files'], service_dir)
