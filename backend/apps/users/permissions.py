from rest_framework.permissions import BasePermission

from .models import UserRole


class IsCustomer(BasePermission):
    message = "A verified customer account is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role == UserRole.USER
            and not user.is_staff
            and hasattr(user, "customer_profile")
        )
