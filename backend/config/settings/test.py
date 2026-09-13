from .base import *  # noqa: F403

# Runtime behavior

DEBUG = False


# Passwords

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# Cache

# Avoid requiring Redis when running unit and integration tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


# Background tasks

# Execute tasks synchronously so failures are visible to the calling test.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True


# Email

# Store messages in memory for assertions without external delivery.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    },
}
