#!/usr/bin/python

# Copyright 2015 Sam Yaple
#
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

DOCUMENTATION = '''
---
module: kolla_docker
short_description: Module for controlling Docker
description:
     - A module targeting at controlling Docker as used by Kolla.
options:
  common_options:
    description:
      - A dict containing common params such as login info
    required: False
    type: dict
    default: dict()
  action:
    description:
      - The action the module should take
    required: True
    type: str
    choices:
      - create_volume
      - pull_image
      - remove_container
      - remove_volume
      - start_container
  api_version:
    description:
      - The version of the api for docker-py to use when contacting docker
    required: False
    type: str
    default: auto
  auth_email:
    description:
      - The email address used to authenticate
    required: False
    type: str
  auth_password:
    description:
      - The password used to authenticate
    required: False
    type: str
  auth_registry:
    description:
      - The registry to authenticate to
    required: False
    type: str
  auth_username:
    description:
      - The username used to authenticate
    required: False
    type: str
  detach:
    description:
      - Detach from the container after it is created
    required: False
    default: True
    type: bool
  name:
    description:
      - Name of the container or volume to manage
    required: False
    type: str
  environment:
    description:
      - The environment to set for the container
    required: False
    type: dict
  image:
    description:
      - Name of the docker image
    required: False
    type: str
  pid_mode:
    description:
      - Set docker pid namespace
    required: False
    type: str
    default: None
    choices:
      - host
  privileged:
    description:
      - Set the container to privileged
    required: False
    default: False
    type: bool
  remove_on_exit:
    description:
      - When not detaching from container, remove on successful exit
    required: False
    default: True
    type: bool
  restart_policy:
    description:
      - Determine what docker does when the container exits
    required: False
    type: str
    choices:
      - never
      - on-failure
      - always
  restart_retries:
    description:
      - How many times to attempt a restart if restart_policy is set
    type: int
    default: 10
  volumes:
    description:
      - Set volumes for docker to use
    required: False
    type: list
  volumes_from:
    description:
      - Name or id of container(s) to use volumes from
    required: True
    type: list
author: Sam Yaple
'''

EXAMPLES = '''
- hosts: kolla_docker
  tasks:
    - name: Start container
      kolla_docker:
        image: ubuntu
        name: test_container
        action: start_container
    - name: Remove container
      kolla_docker:
        name: test_container
        action: remove_container
    - name: Pull image without starting container
      kolla_docker:
        action: pull_container
        image: private-registry.example.com:5000/ubuntu
    - name: Create named volume
        action: create_volume
        name: name_of_volume
    - name: Remove named volume
        action: remove_volume
        name: name_of_volume
'''

import os

import docker


class DockerWorker(object):

    def __init__(self, module):
        self.module = module
        self.params = self.module.params
        self.changed = False

        # TLS not fully implemented
        # tls_config = self.generate_tls()

        options = {
            'version': self.params.get('api_version')
        }

        self.dc = docker.Client(**options)

    def generate_tls(self):
        tls = {'verify': self.params.get('tls_verify')}
        tls_cert = self.params.get('tls_cert'),
        tls_key = self.params.get('tls_key'),
        tls_cacert = self.params.get('tls_cacert')

        if tls['verify']:
            if tlscert:
                self.check_file(tls['tls_cert'])
                self.check_file(tls['tls_key'])
                tls['client_cert'] = (tls_cert, tls_key)
            if tlscacert:
                self.check_file(tls['tls_cacert'])
                tls['verify'] = tls_cacert

        return docker.tls.TLSConfig(**tls)

    def check_file(self, path):
        if not os.path.isfile(path):
            self.module.fail_json(
                failed=True,
                msg='There is no file at "{}"'.format(path)
            )
        if not os.access(path, os.R_OK):
            self.module.fail_json(
                failed=True,
                msg='Permission denied for file at "{}"'.format(path)
            )

    def check_image(self):
        find_image = ':'.join(self.parse_image())
        for image in self.dc.images():
            for image_name in image['RepoTags']:
                if image_name == find_image:
                    return image

    def check_volume(self):
        for vol in self.dc.volumes()['Volumes']:
            if vol['Name'] == self.params.get('name'):
                return vol

    def check_container(self):
        find_name = '/{}'.format(self.params.get('name'))
        for cont in self.dc.containers(all=True):
            if find_name in cont['Names']:
                return cont

    def check_container_differs(self):
        container = self.check_container()
        if not container:
            return True
        container_info = self.dc.inspect_container(self.params.get('name'))

        return (
            self.compare_image(container_info) or
            self.compare_privileged(container_info) or
            self.compare_pid_mode(container_info) or
            self.compare_volumes(container_info) or
            self.compare_volumes_from(container_info) or
            self.compare_environment(container_info)
        )

    def compare_pid_mode(self, container_info):
        new_pid_mode = self.params.get('pid_mode')
        current_pid_mode = container_info['HostConfig'].get('PidMode')
        if not current_pid_mode:
            current_pid_mode = None

        if new_pid_mode != current_pid_mode:
            return True

    def compare_privileged(self, container_info):
        new_privileged = self.params.get('privileged')
        current_privileged = container_info['HostConfig']['Privileged']
        if new_privileged != current_privileged:
            return True

    def compare_image(self, container_info):
        new_image = self.check_image()
        current_image = container_info['Image']
        if new_image['Id'] != current_image:
            return True

    def compare_volumes_from(self, container_info):
        new_vols_from = self.params.get('volumes_from')
        current_vols_from = container_info['HostConfig'].get('VolumesFrom')
        if not new_vols_from:
            new_vols_from = list()
        if not current_vols_from:
            current_vols_from = list()

        if set(current_vols_from).symmetric_difference(set(new_vols_from)):
            return True

    def compare_volumes(self, container_info):
        volumes, binds = self.generate_volumes()
        current_vols = container_info['Config'].get('Volumes')
        current_binds = container_info['HostConfig'].get('Binds')
        if not volumes:
            volumes = list()
        if not current_vols:
            current_vols = list()
        if not current_binds:
            current_binds = list()

        if set(volumes).symmetric_difference(set(current_vols)):
            return True

        new_binds = list()
        if binds:
            for k, v in binds.iteritems():
                new_binds.append("{}:{}:{}".format(k, v['bind'], v['mode']))

        if set(new_binds).symmetric_difference(set(current_binds)):
            return True

    def compare_environment(self, container_info):
        if self.params.get('environment'):
            current_env = dict()
            for kv in container_info['Config'].get('Env', list()):
                k, v = kv.split('=', 1)
                current_env.update({k: v})

            for k, v in self.params.get('environment').iteritems():
                if k not in current_env:
                    return True
                if current_env[k] != v:
                    return True

    def parse_image(self):
        full_image = self.params.get('image')

        if '/' in full_image:
            registry, image = full_image.split('/', 1)
        else:
            image = full_image

        if ':' in image:
            return full_image.rsplit(':', 1)
        else:
            return full_image, 'latest'

    def pull_image(self):
        if self.params.get('auth_username'):
            self.dc.login(
                username=self.params.get('auth_username'),
                password=self.params.get('auth_password'),
                registry=self.params.get('auth_registry'),
                email=self.params.get('auth_email')
            )

        image, tag = self.parse_image()

        statuses = [
            json.loads(line.strip()) for line in self.dc.pull(
                repository=image, tag=tag, stream=True
            )
        ]

        for status in reversed(statuses):
            # NOTE(jeffrey4l): Get the last not empty status with status
            # property
            if status and status.get('status'):
                # NOTE(SamYaple): This allows us to use v1 and v2 docker
                # registries.  Eventually docker will stop supporting v1
                # registries and when that happens we can remove this.
                if 'legacy registry' in status.get('status'):
                    continue
                elif "Downloaded newer image for" in status.get('status'):
                    self.changed = True
                    return
                elif "Image is up to date for" in status.get('status'):
                    return
                else:
                    self.module.fail_json(
                        msg="Invalid status returned from pull",
                        changed=True,
                        failed=True
                    )

    def remove_container(self):
        if self.check_container():
            self.changed = True
            self.dc.remove_container(
                container=self.params.get('name'),
                force=True
            )

    def generate_volumes(self):
        volumes = self.params.get('volumes')
        if not volumes:
            return None, None

        vol_list = list()
        vol_dict = dict()

        for vol in volumes:
            if ':' not in vol:
                vol_list.append(vol)
                continue

            split_vol = vol.split(':')

            if (len(split_vol) == 2
               and ('/' not in split_vol[0] or '/' in split_vol[1])):
                split_vol.append('rw')

            vol_list.append(split_vol[1])
            vol_dict.update({
                split_vol[0]: {
                    'bind': split_vol[1],
                    'mode': split_vol[2]
                }
            })

        return vol_list, vol_dict

    def build_host_config(self, binds):
        options = {
            'network_mode': 'host',
            'pid_mode': self.params.get('pid_mode'),
            'privileged': self.params.get('privileged'),
            'volumes_from': self.params.get('volumes_from')
        }

        if self.params.get('restart_policy') in ['on-failure', 'always']:
            options['restart_policy'] = {
                'Name': self.params.get('restart_policy'),
                'MaximumRetryCount': self.params.get('restart_retries')
            }

        if binds:
            options['binds'] = binds

        return self.dc.create_host_config(**options)

    def build_container_options(self):
        volumes, binds = self.generate_volumes()
        return {
            'detach': self.params.get('detach'),
            'environment': self.params.get('environment'),
            'host_config': self.build_host_config(binds),
            'image': self.params.get('image'),
            'name': self.params.get('name'),
            'volumes': volumes,
            'tty': True
        }

    def create_container(self):
        self.changed = True
        options = self.build_container_options()
        self.dc.create_container(**options)

    def start_container(self):
        if not self.check_image():
            self.pull_image()

        container = self.check_container()
        if container and self.check_container_differs():
            self.remove_container()
            container = self.check_container()

        if not container:
            self.create_container()
            container = self.check_container()

        if not container['Status'].startswith('Up '):
            self.changed = True
            self.dc.start(container=self.params.get('name'))

        # We do not want to detach so we wait around for container to exit
        if not self.params.get('detach'):
            rc = self.dc.wait(self.params.get('name'))
            if rc != 0:
                self.module.fail_json(
                    failed=True,
                    changed=True,
                    msg="Container exited with non-zero return code"
                )
            if self.params.get('remove_on_exit'):
                self.remove_container()

    def create_volume(self):
        if not self.check_volume():
            self.changed = True
            self.dc.create_volume(name=self.params.get('name'), driver='local')

    def remove_volume(self):
        if self.check_volume():
            self.changed = True
            try:
                self.dc.remove_volume(name=self.params.get('name'))
            except docker.errors.APIError as e:
                if e.response.status_code == 409:
                    self.module.fail_json(
                        failed=True,
                        msg="Volume named '{}' is currently in-use".format(
                            self.params.get('name')
                        )
                    )
                raise


def generate_module():
    argument_spec = dict(
        common_options=dict(required=False, type='dict', default=dict()),
        action=dict(requried=True, type='str', choices=['create_volume',
                                                        'pull_image',
                                                        'remove_container',
                                                        'remove_volume',
                                                        'start_container']),
        api_version=dict(required=False, type='str', default='auto'),
        auth_email=dict(required=False, type='str'),
        auth_password=dict(required=False, type='str'),
        auth_registry=dict(required=False, type='str'),
        auth_username=dict(required=False, type='str'),
        detach=dict(required=False, type='bool', default=True),
        name=dict(required=False, type='str'),
        environment=dict(required=False, type='dict'),
        image=dict(required=False, type='str'),
        pid_mode=dict(required=False, type='str', choices=['host']),
        privileged=dict(required=False, type='bool', default=False),
        remove_on_exit=dict(required=False, type='bool', default=True),
        restart_policy=dict(required=False, type='str', choices=['no',
                                                                 'never',
                                                                 'on-failure',
                                                                 'always']),
        restart_retries=dict(required=False, type='int', default=10),
        tls_verify=dict(required=False, type='bool', default=False),
        tls_cert=dict(required=False, type='str'),
        tls_key=dict(required=False, type='str'),
        tls_cacert=dict(required=False, type='str'),
        volumes=dict(required=False, type='list'),
        volumes_from=dict(required=False, type='list')
    )
    required_together = [
        ['tls_cert', 'tls_key']
    ]
    return AnsibleModule(
        argument_spec=argument_spec,
        required_together=required_together
    )


def generate_nested_module():
    module = generate_module()

    # We unnest the common dict and the update it with the other options
    new_args = module.params.get('common_options')
    new_args.update(module._load_params()[0])
    module.params = new_args

    # Override ARGS to ensure new args are used
    global MODULE_ARGS
    global MODULE_COMPLEX_ARGS
    MODULE_ARGS = ''
    MODULE_COMPLEX_ARGS = json.dumps(module.params)

    # Reprocess the args now that the common dict has been unnested
    return generate_module()


def main():
    module = generate_nested_module()

    # TODO(SamYaple): Replace with required_if when Ansible 2.0 lands
    if (module.params.get('action') in ['pull_image', 'start_container']
       and not module.params.get('image')):
        self.module.fail_json(
            msg="missing required arguments: image",
            failed=True
        )
    # TODO(SamYaple): Replace with required_if when Ansible 2.0 lands
    if (module.params.get('action') != 'pull_image'
       and not module.params.get('name')):
        self.module.fail_json(
            msg="missing required arguments: name",
            failed=True
        )

    try:
        dw = DockerWorker(module)
        getattr(dw, module.params.get('action'))()
        module.exit_json(changed=dw.changed)
    except Exception as e:
        module.exit_json(failed=True, changed=True, msg=repr(e))

# import module snippets
from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
