import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import AccountStatus, EmailVerificationOTP


class InvalidOTP(Exception):
    pass


class OTPResendTooSoon(Exception):
    pass


def _digest(user_id, code):
    return salted_hmac(
        key_salt="email-verification-otp",
        value=f"{user_id}:{code}",
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


@transaction.atomic
def issue_email_verification_otp(user, *, enforce_cooldown=True):
    now = timezone.now()
    existing = EmailVerificationOTP.objects.select_for_update().filter(user=user).first()
    cooldown = timedelta(seconds=settings.EMAIL_VERIFICATION_OTP_COOLDOWN_SECONDS)
    if enforce_cooldown and existing and existing.sent_at > now - cooldown:
        raise OTPResendTooSoon

    code = f"{secrets.randbelow(1_000_000):06d}"
    EmailVerificationOTP.objects.update_or_create(
        user=user,
        defaults={
            "code_digest": _digest(user.pk, code),
            "expires_at": now + timedelta(seconds=settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS),
            "attempt_count": 0,
        },
    )
    return code


@transaction.atomic
def verify_email_otp(*, email, code):
    user_model = get_user_model()
    try:
        user = user_model.objects.select_for_update().get(email__iexact=email.strip())
        otp = EmailVerificationOTP.objects.select_for_update().get(user=user)
    except (user_model.DoesNotExist, EmailVerificationOTP.DoesNotExist) as error:
        raise InvalidOTP from error

    if user.is_active or user.status != AccountStatus.ACTIVE:
        raise InvalidOTP
    if otp.expires_at <= timezone.now():
        otp.delete()
        raise InvalidOTP
    if otp.attempt_count >= settings.EMAIL_VERIFICATION_OTP_MAX_ATTEMPTS:
        otp.delete()
        raise InvalidOTP

    if not constant_time_compare(otp.code_digest, _digest(user.pk, code)):
        otp.attempt_count += 1
        if otp.attempt_count >= settings.EMAIL_VERIFICATION_OTP_MAX_ATTEMPTS:
            otp.delete()
        else:
            otp.save(update_fields=["attempt_count"])
        raise InvalidOTP

    user.is_active = True
    user.email_verified_at = timezone.now()
    user.save(update_fields=["is_active", "email_verified_at", "updated_at"])
    otp.delete()
    return user
