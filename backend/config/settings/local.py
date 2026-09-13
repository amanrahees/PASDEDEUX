from . import base
from .base import *  # noqa: F403

# Development behavior

DEBUG = True

CORS_ALLOWED_ORIGINS = base.env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
)


# API documentation

SPECTACULAR_SETTINGS = {
    **base.SPECTACULAR_SETTINGS,
    "SERVE_PERMISSIONS": [
        "rest_framework.permissions.AllowAny",
    ],
}


# Email

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
