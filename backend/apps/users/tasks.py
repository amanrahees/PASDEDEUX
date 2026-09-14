from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_verification_otp_email(user_id, code):
    user = get_user_model().objects.get(pk=user_id)
    if user.is_active:
        return
    send_mail(
        subject="Your PASDEDEUX verification code",
        message=(
            f"Your verification code is {code}. "
            f"It expires in {settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS // 60} minutes. "
            "Do not share this code."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_password_reset_email(user_id):
    user = get_user_model().objects.get(pk=user_id)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    url = f"{settings.AUTH_FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
    send_mail(
        subject="Reset your PASDEDEUX password",
        message=f"Use this link to reset your password: {url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
