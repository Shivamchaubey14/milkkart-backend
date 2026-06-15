"""Role-based DRF permissions for back-office (staff) endpoints.

Roles live on ``accounts.User.role``. An ``admin`` role and any Django superuser
pass every check; other staff roles are scoped to their area. Roles are compared
by string so this module never imports the user model.
"""

from rest_framework.permissions import BasePermission

ADMIN = "admin"
SUPPORT = "support"
OPS = "ops"
WAREHOUSE = "warehouse"


def _has_role(user, allowed):
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    role = getattr(user, "role", None)
    return role == ADMIN or role in allowed


class _RolePermission(BasePermission):
    """Base class: subclasses declare the roles allowed in addition to admin."""

    allowed_roles = ()

    def has_permission(self, request, view):
        return _has_role(request.user, self.allowed_roles)


class IsAdminRole(_RolePermission):
    """Only the admin role (or a superuser)."""

    allowed_roles = ()


class IsSupportAgent(_RolePermission):
    """Support agents handle ratings and tickets."""

    allowed_roles = (SUPPORT,)


class IsOpsManager(_RolePermission):
    """Operations staff view reports and oversee fulfilment."""

    allowed_roles = (OPS,)


class IsWarehouseStaff(_RolePermission):
    """Warehouse (and ops) staff manage inventory."""

    allowed_roles = (WAREHOUSE, OPS)


class IsStaffRole(_RolePermission):
    """Any back-office role."""

    allowed_roles = (SUPPORT, OPS, WAREHOUSE)
