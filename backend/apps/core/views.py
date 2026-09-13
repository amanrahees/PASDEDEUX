from django.core.cache import cache
from django.db import connection
from django.db.utils import DatabaseError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from redis.exceptions import RedisError


def _database_is_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return False

    return True


def _cache_is_ready() -> bool:
    health_key = "system:readiness"

    try:
        cache.set(health_key, "ok", timeout=5)
        return cache.get(health_key) == "ok"
    except RedisError:
        return False


@never_cache
@require_GET
def health_live(request):
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def health_ready(request):
    checks = {
        "database": "ok" if _database_is_ready() else "failed",
        "cache": "ok" if _cache_is_ready() else "failed",
    }

    is_ready = all(result == "ok" for result in checks.values())

    return JsonResponse(
        {
            "status": "ok" if is_ready else "unavailable",
            "checks": checks,
        },
        status=200 if is_ready else 503,
    )
