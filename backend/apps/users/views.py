from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView

from .models import AccountStatus
from .otp import OTPResendTooSoon, issue_email_verification_otp
from .serializers import (
    CurrentUserSerializer,
    EmailSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    RegistrationSerializer,
    VerifyEmailOTPSerializer,
)
from .tasks import send_password_reset_email, send_verification_otp_email


class RegistrationView(GenericAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        code = issue_email_verification_otp(user, enforce_cooldown=False)
        send_verification_otp_email.delay(str(user.pk), code)
        return Response(
            {"detail": "Registration successful. Check your email for the OTP."},
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailOTPView(GenericAPIView):
    serializer_class = VerifyEmailOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_email"

    def post(self, request):
        serializer = VerifyEmailOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "Email verified successfully."})


class ResendVerificationOTPView(GenericAPIView):
    serializer_class = EmailSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_email"

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = (
            get_user_model()
            .objects.filter(
                email__iexact=serializer.validated_data["email"],
                is_active=False,
                status=AccountStatus.ACTIVE,
            )
            .first()
        )
        if user is not None:
            try:
                code = issue_email_verification_otp(user)
            except OTPResendTooSoon:
                pass
            else:
                send_verification_otp_email.delay(str(user.pk), code)
        return Response({"detail": "If an eligible account exists, an OTP has been sent."})


class LoginView(GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response(
            {
                "user": CurrentUserSerializer(user).data,
                "access": serializer.validated_data["access"],
                "refresh": serializer.validated_data["refresh"],
            }
        )


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"


class LogoutView(GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForgotPasswordView(GenericAPIView):
    serializer_class = EmailSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password"

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = (
            get_user_model()
            .objects.filter(
                email__iexact=serializer.validated_data["email"],
                is_active=True,
                status=AccountStatus.ACTIVE,
            )
            .first()
        )
        if user is not None and user.has_usable_password():
            send_password_reset_email.delay(str(user.pk))
        return Response({"detail": "If an eligible account exists, a reset email has been sent."})


class ResetPasswordView(GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password reset successfully."})


class CurrentUserView(GenericAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)
