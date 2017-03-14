# Copyright 2017 AT&T Corporation.
# All Rights Reserved.
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

from tempest.lib import decorators
from tempest import test

from patrole_tempest_plugin import rbac_rule_validation
from patrole_tempest_plugin.tests.api.compute import rbac_base


class InstanceUsagesAuditLogAdminRbacTest(
        rbac_base.BaseV2ComputeAdminRbacTest):

    @classmethod
    def skip_checks(cls):
        super(InstanceUsagesAuditLogAdminRbacTest, cls).skip_checks()
        if not test.is_extension_enabled('os-instance-usage-audit-log',
                                         'compute'):
            msg = "os-instance-usage-audit-log extension not enabled."
            raise cls.skipException(msg)

    @classmethod
    def setup_clients(cls):
        super(InstanceUsagesAuditLogAdminRbacTest, cls).setup_clients()
        cls.client = cls.instance_usages_audit_log_client

    @decorators.idempotent_id('c80246c0-5c13-4ab0-97ba-91551cd53dc1')
    @rbac_rule_validation.action(
        service="nova", rule="os_compute_api:os-instance-usage-audit-log")
    def test_list_instance_usage_audit_logs(self):
        self.rbac_utils.switch_role(self, switchToRbacRole=True)
        self.client.list_instance_usage_audit_logs()
        ["instance_usage_audit_logs"]
