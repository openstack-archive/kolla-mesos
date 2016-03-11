#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import re


"""
Guidelines for writing new hacking checks

- Use only for kolla-mesos specific tests. OpenStack general tests
  should be submitted to the common 'hacking' module.
- Pick numbers in the range H3xx. Find the current test with
  the highest allocated number and then pick the next value.
- Keep the test method code in the source file ordered based
  on the H3xx value.
- List the new rule in the top level HACKING.rst file
- Add test cases for each new rule to kolla_mesos/tests/test_hacking.py

"""


def check_python3_no_iteritems(logical_line):
    msg = ("H301: Use six.iteritems() instead of dict.iteritems().")

    if re.search(r".*\.iteritems\(\)", logical_line):
        yield(0, msg)


def check_python3_no_iterkeys(logical_line):
    msg = ("H302: Use six.iterkeys() instead of dict.iterkeys().")

    if re.search(r".*\.iterkeys\(\)", logical_line):
        yield(0, msg)


def check_python3_no_itervalues(logical_line):
    msg = ("H303: Use six.itervalues() instead of dict.itervalues().")

    if re.search(r".*\.itervalues\(\)", logical_line):
        yield(0, msg)


def factory(register):
    register(check_python3_no_iteritems)
    register(check_python3_no_iterkeys)
    register(check_python3_no_itervalues)
