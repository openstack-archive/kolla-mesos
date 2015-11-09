#!/usr/bin/env python

#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ConfigParser
import datetime
import logging
import os
import shutil
import StringIO
import tempfile
import time
import yaml

import mock

from kolla_mesos import render
from kolla_mesos import utils


logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


class KollaWorker(object):

    def __init__(self, config, profiles):
        self.base_dir = os.path.abspath(utils.find_base_dir())
        self.config_dir = os.path.join(self.base_dir, 'config')
        LOG.debug("Kolla base directory: " + self.base_dir)
        self.namespace = config['namespace']
        self.base = config['base']
        self.install_type = config['install_type']
        self.image_prefix = self.base + '-' + config['install_type'] + '-'
        self.build_config = config
        self.profiles = profiles

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = time.time()
        ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='kolla-' + ts)
        # Note "odir" == output directory
        self.config_odir = os.path.join(self.temp_dir, 'config')
        self.marathon_odir = os.path.join(self.temp_dir, 'marathon')
        utils.mkdir_p(self.config_odir)
        utils.mkdir_p(self.marathon_odir)
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

    def get_services(self, project):
        project_dir = os.path.join(self.base_dir,
                                   'config', project, 'templates')
        for root, dirs, names in os.walk(project_dir):
            LOG.info(names)
            for name in names:
                if name.endswith('.json.j2') and name.startswith(project):
                    sname = name.split('.')[0]
                    if len(sname) > len(project):
                        yield sname.replace('%s-' % project, '')
                    if len(sname) == len(project):
                        yield project  # project == service name

    def get_jinja_vars(self, proj):
        # order for per-project variables (each overrides the previous):
        # 1. /etc/kolla/globals.yml
        # 2. config/all.yml
        # 3. config/<project>/defaults/main.yml
        with open(utils.find_config_file('globals.yml'), 'r') as gf:
            global_vars = yaml.load(gf)

        all_yml_name = os.path.join(self.config_dir, 'all.yml')
        all_vars = yaml.load(render.jinja_render(all_yml_name, global_vars))

        proj_yml_name = os.path.join(self.config_dir, proj,
                                     'defaults', 'main.yml')
        if not os.path.exists(proj_yml_name):
            LOG.warn('path missing %s' % proj_yml_name)
        proj_vars = yaml.load(render.jinja_render(proj_yml_name, all_vars,
                                                  extra=global_vars))

        jvars = all_vars
        jvars.update(proj_vars)
        jvars.update(global_vars)
        # override node_config_directory to empty
        jvars.update({'node_config_directory': ''})
        return jvars

    def parse_extra_config(self, proj, service, jvars):
        conf_path = os.path.join(self.config_dir, proj,
                                 service + '_config.yml')
        config = yaml.load(render.jinja_render(conf_path, jvars))
        # for each, parse and copy to dest
        for copy_file in config:
            src_path = os.path.join(self.base_dir,
                                    copy_file['template']['src'])
            src_content = render.jinja_render(src_path, jvars)
            dest_file = copy_file['template']['dest']
            if dest_file.startswith('/'):
                dest_file = dest_file[1:]
            dest = os.path.join(self.config_odir,
                                dest_file)
            utils.mkdir_p(os.path.dirname(dest))
            with open(dest, 'w') as f:
                f.write(src_content)

    def parse_app_files(self):

        def get_possible_files(proj, service):
            yield "/etc/kolla/config/global.conf"
            yield "/etc/kolla/config/database.conf"
            yield "/etc/kolla/config/messaging.conf"
            yield "/etc/kolla/config/%s.conf" % proj
            yield "/etc/kolla/config/%s/%s.conf" % (proj, service)
            yield os.path.join(self.config_dir, proj, 'templates',
                               proj + '.conf.j2')

        for proj in self.get_projects():
            proj_dir = os.path.join(self.config_dir, proj)
            if not os.path.exists(proj_dir):
                continue

            jinja_vars = self.get_jinja_vars(proj)

            for service in self.get_services(proj):
                # override container_config_directory
                cont_conf_dir = 'zk://localhost/%s/%s' % (proj, service)
                jinja_vars['container_config_directory'] = cont_conf_dir

                # 1. do the service etc config file
                config_p = ConfigParser.ConfigParser()
                dest_file = os.path.join(self.config_odir, service,
                                         proj + '.conf')
                for conf_file in get_possible_files(proj, service):
                    if not os.path.exists(conf_file):
                        LOG.warn('path missing %s' % conf_file)
                        continue

                    # TODO(asalkeld) turn into zookeeper variables
                    hostvars = mock.MagicMock()
                    groups = mock.MagicMock()
                    values = {'hostvars': hostvars,
                              'groups': groups}

                    content = render.jinja_render(conf_file, jinja_vars,
                                                  extra=values)
                    config_p.readfp(StringIO.StringIO(content))

                    if hostvars.mock_calls:
                        LOG.info('hostvars: %s' % hostvars.mock_calls)
                    if groups.mock_calls:
                        LOG.info('groups: %s' % groups.mock_calls)

                LOG.info(dest_file)

                utils.mkdir_p(os.path.dirname(dest_file))
                with open(dest_file, 'w') as f:
                    config_p.write(f)

                # 2. extra etc config files
                #    (was in config.yml)
                self.parse_extra_config(proj, service, jinja_vars)

                # 3. do the service's config.json (now KOLLA_CONFIG)
                kc_name = os.path.join(self.config_dir,
                                       proj, 'templates',
                                       '%s-%s.json.j2' % (proj, service))
                if proj == service:
                    kc_name = os.path.join(self.config_dir,
                                           proj, 'templates',
                                           '%s.json.j2' % (proj))

                kolla_config = render.jinja_render(kc_name, jinja_vars)

                # 4. parse the marathon app file and add the KOLLA_CONFIG
                values = {'kolla_config': kolla_config}
                app_file = os.path.join(self.base_dir, 'marathon', proj,
                                        service + '.json.j2')
                content = render.jinja_render(app_file, jinja_vars,
                                              extra=values)
                dest_file = os.path.join(self.temp_dir, 'marathon', proj,
                                         service + '.json')
                utils.mkdir_p(os.path.dirname(dest_file))
                with open(dest_file, 'w') as f:
                    f.write(content)

    def cleanup(self):
        """Remove temp files"""
        shutil.rmtree(self.temp_dir)
