from django.contrib.auth import get_user_model
from django.db import transaction

from .models import CustomerProfile, ShoppingPreference


@transaction.atomic
def create_customer_account(
    *,
    email,
    password,
    first_name="",
    last_name="",
    phone="",
    shopping_preference=ShoppingPreference.NO_PREFERENCE,
):
    User = get_user_model()

    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

    CustomerProfile.objects.create(
        user=user,
        phone=phone,
        shopping_preference=shopping_preference,
    )

    return user
