from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AddressViewSet, CustomerProfileView

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [path("profile/", CustomerProfileView.as_view(), name="customer-profile")]
urlpatterns += router.urls
