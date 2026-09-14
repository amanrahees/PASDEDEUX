from django.urls import path

from .views import (
    CurrentUserView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RefreshView,
    RegistrationView,
    ResendVerificationOTPView,
    ResetPasswordView,
    VerifyEmailOTPView,
)

app_name = "users"

urlpatterns = [
    path("register/", RegistrationView.as_view(), name="register"),
    path("verify-email/", VerifyEmailOTPView.as_view(), name="verify-email"),
    path(
        "resend-verification/",
        ResendVerificationOTPView.as_view(),
        name="resend-verification",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("me/", CurrentUserView.as_view(), name="me"),
]
