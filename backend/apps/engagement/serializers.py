from rest_framework import serializers

from apps.catalog.models import Product, ProductStatus
from apps.catalog.serializers import ProductListSerializer
from apps.orders.models import OrderStatus

from .models import ProductReview, RecentlyViewedProduct, WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product",
        queryset=Product.objects.filter(status=ProductStatus.ACTIVE, category__is_active=True),
        write_only=True,
    )

    class Meta:
        model = WishlistItem
        fields = ("id", "product", "product_id", "created_at")
        read_only_fields = ("id", "created_at")


class ProductReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = (
            "id",
            "user_name",
            "rating",
            "title",
            "body",
            "is_verified_purchase",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user_name",
            "is_verified_purchase",
            "status",
            "created_at",
            "updated_at",
        )

    def get_user_name(self, review):
        return f"{review.user.first_name} {review.user.last_name}".strip() or "Customer"

    def create(self, validated_data):
        user = self.context["request"].user
        product = self.context["product"]
        verified = product.variants.filter(
            order_items__order__user=user,
            order_items__order__status__in=(
                OrderStatus.PAID,
                OrderStatus.PROCESSING,
                OrderStatus.SHIPPED,
                OrderStatus.DELIVERED,
            ),
        ).exists()
        return ProductReview.objects.create(
            user=user,
            product=product,
            is_verified_purchase=verified,
            **validated_data,
        )


class RecentlyViewedSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = RecentlyViewedProduct
        fields = ("product", "view_count", "last_viewed_at")
