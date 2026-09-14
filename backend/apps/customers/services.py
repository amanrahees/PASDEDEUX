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
    user_model = get_user_model()

    user = user_model.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_active=False,
        role="USER",
        status="ACTIVE",
    )

    profile = CustomerProfile(
        user=user,
        phone=phone,
        shopping_preference=shopping_preference,
    )
    profile.full_clean()
    profile.save()

    return user
