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

import abc
from contextlib import contextmanager
import debtcollector.removals
import six
import time

from oslo_log import log as logging
from oslo_utils import excutils

from tempest import clients
from tempest.common import credentials_factory as credentials
from tempest import config

from patrole_tempest_plugin import rbac_exceptions

CONF = config.CONF
LOG = logging.getLogger(__name__)


class RbacUtils(object):
    """Utility class responsible for switching ``os_primary`` role.

    This class is responsible for overriding the value of the primary Tempest
    credential's role (i.e. ``os_primary`` role). By doing so, it is possible
    to seamlessly swap between admin credentials, needed for setup and clean
    up, and primary credentials, needed to perform the API call which does
    policy enforcement. The primary credentials always cycle between roles
    defined by ``CONF.identity.admin_role`` and
    ``CONF.patrole.rbac_test_role``.
    """

    def __init__(self, test_obj):
        """Constructor for ``RbacUtils``.

        :param test_obj: An instance of `tempest.test.BaseTestCase`.
        """
        # Intialize the admin roles_client to perform role switching.
        admin_mgr = clients.Manager(
            credentials.get_configured_admin_credentials())
        if test_obj.get_identity_version() == 'v3':
            admin_roles_client = admin_mgr.roles_v3_client
        else:
            admin_roles_client = admin_mgr.roles_client

        self.admin_roles_client = admin_roles_client
        self._override_role(test_obj, False)

    admin_role_id = None
    rbac_role_id = None

    @contextmanager
    def override_role(self, test_obj):
        """Override the role used by ``os_primary`` Tempest credentials.

        Temporarily change the role used by ``os_primary`` credentials to:
          * ``[patrole] rbac_test_role`` before test execution
          * ``[identity] admin_role`` after test execution

        Automatically switches to admin role after test execution.

        :param test_obj: Instance of ``tempest.test.BaseTestCase``.
        :returns: None

        .. warning::

            This function can alter user roles for pre-provisioned credentials.
            Work is underway to safely clean up after this function.

        Example::

            @rbac_rule_validation.action(service='test',
                                         rule='a:test:rule')
            def test_foo(self):
                # Allocate test-level resources here.
                with self.rbac_utils.override_role(self):
                    # The role for `os_primary` has now been overriden. Within
                    # this block, call the API endpoint that enforces the
                    # expected policy specified by "rule" in the decorator.
                    self.foo_service.bar_api_call()
                # The role is switched back to admin automatically. Note that
                # if the API call above threw an exception, any code below this
                # point in the test is not executed.
        """
        self._override_role(test_obj, True)
        try:
            # Execute the test.
            yield
        finally:
            # This code block is always executed, no matter the result of the
            # test. Automatically switch back to the admin role for test clean
            # up.
            self._override_role(test_obj, False)

    @debtcollector.removals.remove(removal_version='Rocky')
    def switch_role(self, test_obj, toggle_rbac_role):
        """Switch the role used by `os_primary` Tempest credentials.

        Switch the role used by `os_primary` credentials to:
          * admin if `toggle_rbac_role` is False
          * `CONF.patrole.rbac_test_role` if `toggle_rbac_role` is True

        :param test_obj: test object of type tempest.lib.base.BaseTestCase
        :param toggle_rbac_role: role to switch `os_primary` Tempest creds to
        """
        self._override_role(test_obj, toggle_rbac_role)

    def _override_role(self, test_obj, toggle_rbac_role=False):
        """Private helper for overriding ``os_primary`` Tempest credentials.

        :param test_obj: test object of type tempest.lib.base.BaseTestCase
        :param toggle_rbac_role: Boolean value that controls the role that
            overrides default role of ``os_primary`` credentials.
            * If True: role is set to ``[patrole] rbac_test_role``
            * If False: role is set to ``[identity] admin_role``
        """
        self.user_id = test_obj.os_primary.credentials.user_id
        self.project_id = test_obj.os_primary.credentials.tenant_id
        self.token = test_obj.os_primary.auth_provider.get_token()

        LOG.debug('Overriding role to: %s.', toggle_rbac_role)
        role_already_present = False

        try:
            if not all([self.admin_role_id, self.rbac_role_id]):
                self._get_roles_by_name()

            target_role = (
                self.rbac_role_id if toggle_rbac_role else self.admin_role_id)
            role_already_present = self._list_and_clear_user_roles_on_project(
                target_role)

            # Do not override roles if `target_role` already exists.
            if not role_already_present:
                self._create_user_role_on_project(target_role)
        except Exception as exp:
            with excutils.save_and_reraise_exception():
                LOG.exception(exp)
        finally:
            test_obj.os_primary.auth_provider.clear_auth()
            # Fernet tokens are not subsecond aware so sleep to ensure we are
            # passing the second boundary before attempting to authenticate.
            # Only sleep if a token revocation occurred as a result of role
            # overriding. This will optimize test runtime in the case where
            # ``[identity] admin_role`` == ``[patrole] rbac_test_role``.
            if not role_already_present:
                time.sleep(1)
            test_obj.os_primary.auth_provider.set_auth()

    def _get_roles_by_name(self):
        available_roles = self.admin_roles_client.list_roles()
        admin_role_id = rbac_role_id = None

        for role in available_roles['roles']:
            if role['name'] == CONF.patrole.rbac_test_role:
                rbac_role_id = role['id']
            if role['name'] == CONF.identity.admin_role:
                admin_role_id = role['id']

        if not all([admin_role_id, rbac_role_id]):
            msg = ("Roles defined by `[patrole] rbac_test_role` and "
                   "`[identity] admin_role` must be defined in the system.")
            raise rbac_exceptions.RbacResourceSetupFailed(msg)

        self.admin_role_id = admin_role_id
        self.rbac_role_id = rbac_role_id

    def _create_user_role_on_project(self, role_id):
        self.admin_roles_client.create_user_role_on_project(
            self.project_id, self.user_id, role_id)

    def _list_and_clear_user_roles_on_project(self, role_id):
        roles = self.admin_roles_client.list_user_roles_on_project(
            self.project_id, self.user_id)['roles']
        role_ids = [role['id'] for role in roles]

        # NOTE(felipemonteiro): We do not use ``role_id in role_ids`` here to
        # avoid over-permission errors: if the current list of roles on the
        # project includes "admin" and "Member", and we are switching to the
        # "Member" role, then we must delete the "admin" role. Thus, we only
        # return early if the user's roles on the project are an exact match.
        if [role_id] == role_ids:
            return True

        for role in roles:
            self.admin_roles_client.delete_role_from_user_on_project(
                self.project_id, self.user_id, role['id'])

        return False


def is_admin():
    """Verifies whether the current test role equals the admin role.

    :returns: True if ``rbac_test_role`` is the admin role.
    """
    return CONF.patrole.rbac_test_role == CONF.identity.admin_role


@six.add_metaclass(abc.ABCMeta)
class RbacAuthority(object):
    """Class for validating whether a given role can perform a policy action.

    Any class that extends ``RbacAuthority`` provides the logic for determining
    whether a role has permissions to execute a policy action.
    """

    @abc.abstractmethod
    def allowed(self, rule, role):
        """Determine whether the role should be able to perform the API.

        :param rule: The name of the policy enforced by the API.
        :param role: The role used to determine whether ``rule`` can be
            executed.
        :returns: True if the ``role`` has permissions to execute
            ``rule``, else False.
        """
