from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CartItemCollectionView, CartItemDetailView, CartView, CheckoutView, OrderViewSet

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemCollectionView.as_view(), name="cart-items"),
    path("cart/items/<uuid:item_id>/", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
]
urlpatterns += router.urls
