from django.urls import path

from .views import (
    ProductReviewView,
    RecentlyViewedView,
    RecommendationView,
    WishlistItemView,
    WishlistView,
)

urlpatterns = [
    path("wishlist/", WishlistView.as_view(), name="wishlist"),
    path("wishlist/<uuid:product_id>/", WishlistItemView.as_view(), name="wishlist-item"),
    path("products/<slug:slug>/reviews/", ProductReviewView.as_view(), name="product-reviews"),
    path("recently-viewed/", RecentlyViewedView.as_view(), name="recently-viewed"),
    path("recommendations/", RecommendationView.as_view(), name="recommendations"),
]
