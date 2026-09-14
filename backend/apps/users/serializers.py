from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from apps.customers.models import ShoppingPreference
from apps.customers.services import create_customer_account

from .models import AccountStatus
from .otp import InvalidOTP, verify_email_otp


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    phone = serializers.CharField(max_length=16, allow_blank=True, required=False)
    shopping_preference = serializers.ChoiceField(
        choices=ShoppingPreference.choices,
        default=ShoppingPreference.NO_PREFERENCE,
    )

    def validate_email(self, value):
        user_model = get_user_model()
        email = user_model.objects.normalize_email(value).lower()
        if user_model.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        candidate = get_user_model()(
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)}) from error
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        return create_customer_account(**validated_data)


class VerifyEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(regex=r"^\d{6}$", write_only=True)

    def validate(self, attrs):
        try:
            attrs["user"] = verify_email_otp(email=attrs["email"], code=attrs["otp"])
        except InvalidOTP as error:
            raise serializers.ValidationError(
                {"otp": "The verification code is invalid or expired."}
            ) from error
        return attrs


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = get_user_model().objects.filter(email__iexact=attrs["email"].strip()).first()
        if user is None or not user.check_password(attrs["password"]):
            raise AuthenticationFailed("Invalid email or password.")
        if user.status != AccountStatus.ACTIVE:
            raise PermissionDenied("This account is not available.")
        if not user.is_active:
            raise PermissionDenied("Verify your email before logging in.")

        refresh = RefreshToken.for_user(user)
        attrs.update(
            user=user,
            access=str(refresh.access_token),
            refresh=str(refresh),
        )
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def save(self):
        try:
            RefreshToken(self.validated_data["refresh"]).blacklist()
        except TokenError as error:
            raise serializers.ValidationError(
                {"refresh": "The refresh token is invalid or expired."}
            ) from error


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        user_model = get_user_model()
        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = user_model.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, user_model.DoesNotExist) as error:
            raise serializers.ValidationError(
                {"token": "This reset link is invalid or expired."}
            ) from error
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "This reset link is invalid or expired."})
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)}) from error
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password", "updated_at"])
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        return user


class CurrentUserSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source="customer_profile.phone", read_only=True)
    shopping_preference = serializers.CharField(
        source="customer_profile.shopping_preference",
        read_only=True,
    )

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "status",
            "phone",
            "shopping_preference",
            "email_verified_at",
            "date_joined",
        )
        read_only_fields = fields
