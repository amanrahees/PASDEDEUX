from django.urls import path

from .views import health_live, health_ready

app_name = "core"

urlpatterns = [
    path("live/", health_live, name="live"),
    path("ready/", health_ready, name="ready"),
]
