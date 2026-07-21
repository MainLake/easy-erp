from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Allow only users with the 'admin' role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'admin'
        )


class IsOperator(BasePermission):
    """Allow users with 'admin' or 'operator' role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('admin', 'operator')
        )


class IsViewer(BasePermission):
    """Allow any authenticated user regardless of role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
        )
