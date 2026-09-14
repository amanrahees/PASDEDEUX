import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.catalog.models import Product


class WishlistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_items")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_product")
        ]

    def __str__(self):
        return f"{self.user.email}: {self.product.name}"


class ReviewStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class ProductReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_reviews"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(max_length=3000)
    is_verified_purchase = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="one_review_per_product")
        ]
        indexes = [models.Index(fields=["product", "status", "-created_at"])]

    def __str__(self):
        return f"{self.rating}/5 for {self.product.name}"


class RecentlyViewedProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recently_viewed_products"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recent_views")
    view_count = models.PositiveIntegerField(default=1)
    last_viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-last_viewed_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_recent_product")
        ]
        indexes = [models.Index(fields=["user", "-last_viewed_at"])]

    def __str__(self):
        return f"{self.user.email}: {self.product.name}"
