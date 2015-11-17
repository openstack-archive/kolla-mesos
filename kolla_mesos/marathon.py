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

from dcos import marathon

from kolla_mesos.common import config_utils


def create_client():
    """Create Marathon client object with parameters from configuration"""
    conf = config_utils.load_marathon_config()
    return marathon.Client(conf['url'], timeout=float(conf['timeout']))
