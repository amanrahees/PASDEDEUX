from datetime import timedelta
from pathlib import Path

import environ

# Paths and environment

BASE_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BASE_DIR.parent

env = environ.Env()
env_file = ROOT_DIR / ".env"

# Process environment variables take precedence over values in this file.
if env_file.exists():
    environ.Env.read_env(env_file)


# Core Django
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Applications

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Local apps
    "apps.users",
    "apps.core",
    "apps.customers",
    "apps.catalog",
    "apps.orders",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# Templates

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# Database

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True


# Authentication and password validation

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static and uploaded files

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# DRF Configuration

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("AUTH_RATE", default="20/hour"),
        "auth_email": env("AUTH_EMAIL_RATE", default="10/hour"),
        "auth_password": env("AUTH_PASSWORD_RATE", default="10/hour"),
        "auth_refresh": env("AUTH_REFRESH_RATE", default="120/hour"),
        "anon": env("API_ANON_RATE", default="100/hour"),
        "user": env("API_USER_RATE", default="1000/hour"),
    },
}


# Auth Tokens

AUTH_SESSION_LIFETIME = timedelta(days=env.int("AUTH_SESSION_DAYS", default=30))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=10)),
    "REFRESH_TOKEN_LIFETIME": AUTH_SESSION_LIFETIME,
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "USER_AUTHENTICATION_RULE": "apps.users.authentication.jwt_user_authentication_rule",
}

EMAIL_VERIFICATION_OTP_TTL_SECONDS = env.int("EMAIL_VERIFICATION_OTP_TTL_SECONDS", default=600)
EMAIL_VERIFICATION_OTP_COOLDOWN_SECONDS = env.int(
    "EMAIL_VERIFICATION_OTP_COOLDOWN_SECONDS", default=60
)
EMAIL_VERIFICATION_OTP_MAX_ATTEMPTS = env.int("EMAIL_VERIFICATION_OTP_MAX_ATTEMPTS", default=5)
AUTH_FRONTEND_URL = env("AUTH_FRONTEND_URL", default="http://localhost:3000")
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=3600)


# API documentation

SPECTACULAR_SETTINGS = {
    "TITLE": "PASDEDEUX API",
    "DESCRIPTION": "API for the PASDEDEUX Web Application",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "SERVE_PERMISSIONS": [
        "rest_framework.permissions.IsAdminUser",
    ],
}


# Browser clients

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = env.bool("CORS_ALLOW_CREDENTIALS", default=False)
CORS_URLS_REGEX = r"^/api/.*$"

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])


# Cache

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "TIMEOUT": env.int("CACHE_DEFAULT_TIMEOUT", default=300),
        "KEY_PREFIX": env("CACHE_KEY_PREFIX", default="pasdedeux"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": False,
        },
    },
}


# Background tasks

CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=270)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=300)
CELERY_RESULT_EXPIRES = env.int("CELERY_RESULT_EXPIRES", default=3600)

CELERY_WORKER_CONCURRENCY = env.int("CELERY_WORKER_CONCURRENCY", default=2)
CELERY_WORKER_PREFETCH_MULTIPLIER = env.int(
    "CELERY_WORKER_PREFETCH_MULTIPLIER",
    default=1,
)
CELERY_WORKER_MAX_TASKS_PER_CHILD = env.int(
    "CELERY_WORKER_MAX_TASKS_PER_CHILD",
    default=100,
)


# Email

MAILERS = {
    "default": {
        "BACKEND": env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"),
        "OPTIONS": {
            "host": env("EMAIL_HOST", default="localhost"),
            "port": env.int("EMAIL_PORT", default=587),
            "username": env("EMAIL_HOST_USER", default=""),
            "password": env("EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env.bool("EMAIL_USE_TLS", default=True),
            "timeout": env.int("EMAIL_TIMEOUT", default=10),
        },
    },
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Pasdedeux <no-reply@pasdedeux.com>")


# Defaults

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
