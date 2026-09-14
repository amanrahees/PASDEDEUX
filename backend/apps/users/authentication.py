from .models import AccountStatus


def jwt_user_authentication_rule(user):
    return user is not None and user.is_active and user.status == AccountStatus.ACTIVE
