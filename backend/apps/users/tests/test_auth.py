from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.customers.models import CustomerProfile

from ..models import EmailVerificationOTP
from ..otp import issue_email_verification_otp


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def active_user(db):
    return get_user_model().objects.create_user(
        email="customer@example.com",
        password="SafePassword!493",
        is_active=True,
        email_verified_at="2026-01-01T00:00:00Z",
    )


@pytest.mark.django_db
@patch("apps.users.views.send_verification_otp_email.delay")
def test_registration_creates_inactive_customer(mock_send, api_client):
    response = api_client.post(
        reverse("users:register"),
        {
            "email": "New.Customer@example.com",
            "password": "SafePassword!493",
            "password_confirm": "SafePassword!493",
            "first_name": "New",
            "last_name": "Customer",
        },
        format="json",
    )

    assert response.status_code == 201
    user = get_user_model().objects.get(email="new.customer@example.com")
    assert user.is_active is False
    assert CustomerProfile.objects.filter(user=user).exists()
    assert EmailVerificationOTP.objects.filter(user=user).exists()
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_otp_verification_activates_user(api_client):
    user = get_user_model().objects.create_user(
        email="verify@example.com",
        password="SafePassword!493",
        is_active=False,
    )
    code = issue_email_verification_otp(user, enforce_cooldown=False)

    response = api_client.post(
        reverse("users:verify-email"),
        {"email": user.email, "otp": code},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_active is True
    assert user.email_verified_at is not None
    assert not EmailVerificationOTP.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_unverified_user_cannot_login(api_client):
    get_user_model().objects.create_user(
        email="unverified@example.com",
        password="SafePassword!493",
        is_active=False,
    )

    response = api_client.post(
        reverse("users:login"),
        {"email": "unverified@example.com", "password": "SafePassword!493"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_login_and_logout_blacklists_refresh(api_client, active_user):
    login = api_client.post(
        reverse("users:login"),
        {"email": active_user.email, "password": "SafePassword!493"},
        format="json",
    )
    assert login.status_code == 200

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    logout = api_client.post(
        reverse("users:logout"),
        {"refresh": login.data["refresh"]},
        format="json",
    )
    assert logout.status_code == 204
    assert BlacklistedToken.objects.count() == 1


@pytest.mark.django_db
@patch("apps.users.views.send_password_reset_email.delay")
def test_forgot_password_is_generic(mock_send, api_client, active_user):
    known = api_client.post(
        reverse("users:forgot-password"),
        {"email": active_user.email},
        format="json",
    )
    unknown = api_client.post(
        reverse("users:forgot-password"),
        {"email": "missing@example.com"},
        format="json",
    )

    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data
    mock_send.assert_called_once_with(str(active_user.pk))


@pytest.mark.django_db
def test_password_reset_changes_password_and_revokes_refresh(api_client, active_user):
    RefreshToken.for_user(active_user)
    uid = urlsafe_base64_encode(force_bytes(active_user.pk))
    token = default_token_generator.make_token(active_user)

    response = api_client.post(
        reverse("users:reset-password"),
        {
            "uid": uid,
            "token": token,
            "password": "NewSafePassword!572",
            "password_confirm": "NewSafePassword!572",
        },
        format="json",
    )

    assert response.status_code == 200
    active_user.refresh_from_db()
    assert active_user.check_password("NewSafePassword!572")
    assert BlacklistedToken.objects.count() == 1
