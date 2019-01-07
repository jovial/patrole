# Copyright 2010-2011 OpenStack Foundation
# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
# Copyright 2017 AT&T Corporation.
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

from tempest.tests import base


class TestCase(base.TestCase):

    """Test case base class for all unit tests."""

    def get_all_needed_roles(self, roles):
        role_inferences_mapping = {
            "admin": {"member", "reader"},
            "member": {"reader"}
        }
        res = set(r.lower() for r in roles)
        for role in res.copy():
            res.update(role_inferences_mapping.get(role, set()))
        return list(res)
