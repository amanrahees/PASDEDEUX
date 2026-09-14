from django.urls import include, path

urlpatterns = [
    path("v1/auth/", include("apps.users.urls")),
    path("v1/", include("apps.catalog.urls")),
    path("v1/", include("apps.customers.urls")),
    path("v1/", include("apps.orders.urls")),
    path("v1/", include("apps.engagement.urls")),
]
