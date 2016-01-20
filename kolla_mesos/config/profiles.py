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

from oslo_config import cfg


CONF = cfg.CONF
profiles_opts = [
    cfg.ListOpt('infra',
                default=['ceph', 'data', 'mariadb', 'haproxy', 'keepalived',
                         'kolla-toolbox', 'memcached', 'mongodb',
                         'openvswitch', 'rabbitmq']),
    cfg.ListOpt('main',
                default=['cinder', 'ceilometer', 'glance', 'heat', 'horizon',
                         'keystone', 'neutron', 'nova', 'swift']),
    cfg.ListOpt('aux',
                default=['designate', 'gnocchi', 'ironic', 'magnum', 'zaqar']),
    cfg.ListOpt('default',
                default=['data', 'kolla-toolbox', 'glance', 'haproxy', 'heat',
                         'horizon', 'keepalived', 'keystone', 'memcached',
                         'mariadb', 'neutron', 'nova', 'openvswitch',
                         'rabbitmq']),
    cfg.ListOpt('gate',
                default=['ceph', 'cinder', 'data', 'dind', 'glance', 'haproxy',
                         'heat', 'horizon', 'keepalived', 'keystone',
                         'kolla-toolbox', 'mariadb', 'memcached', 'neutron',
                         'nova', 'openvswitch', 'rabbitmq'])
]
profiles_opt_group = cfg.OptGroup(name='profiles',
                                  title='Common sets of images')
CONF.register_group(profiles_opt_group)
CONF.register_cli_opts(profiles_opts, profiles_opt_group)
CONF.register_opts(profiles_opts, profiles_opt_group)
