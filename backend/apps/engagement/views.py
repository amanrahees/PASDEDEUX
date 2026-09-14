from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny

from apps.catalog.models import Product, ProductStatus
from apps.catalog.serializers import ProductListSerializer
from apps.users.permissions import IsCustomer

from .models import ProductReview, RecentlyViewedProduct, ReviewStatus, WishlistItem
from .serializers import (
    ProductReviewSerializer,
    RecentlyViewedSerializer,
    WishlistItemSerializer,
)


class WishlistView(generics.ListCreateAPIView):
    serializer_class = WishlistItemSerializer
    permission_classes = [IsCustomer]

    def get_queryset(self):
        return (
            WishlistItem.objects.filter(user=self.request.user)
            .select_related("product__category", "product__brand")
            .prefetch_related("product__images", "product__variants")
        )

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(user=self.request.user)
        except IntegrityError as error:
            raise ValidationError(
                {"product_id": "This product is already in the wishlist."}
            ) from error


class WishlistItemView(generics.DestroyAPIView):
    permission_classes = [IsCustomer]

    def get_object(self):
        return get_object_or_404(
            WishlistItem, user=self.request.user, product_id=self.kwargs["product_id"]
        )


class ProductReviewView(generics.ListCreateAPIView):
    serializer_class = ProductReviewSerializer

    def get_permissions(self):
        permission_classes = [IsCustomer] if self.request.method == "POST" else [AllowAny]
        return [permission() for permission in permission_classes]

    def get_product(self):
        return get_object_or_404(
            Product,
            slug=self.kwargs["slug"],
            status=ProductStatus.ACTIVE,
            category__is_active=True,
        )

    def get_queryset(self):
        return ProductReview.objects.filter(
            product=self.get_product(), status=ReviewStatus.APPROVED
        ).select_related("user")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["product"] = self.get_product()
        return context

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as error:
            raise ValidationError("You have already reviewed this product.") from error


class RecentlyViewedView(generics.ListAPIView):
    serializer_class = RecentlyViewedSerializer
    permission_classes = [IsCustomer]

    def get_queryset(self):
        return (
            RecentlyViewedProduct.objects.filter(user=self.request.user)
            .select_related("product__category", "product__brand")
            .prefetch_related("product__images", "product__variants")[:20]
        )


class RecommendationView(generics.GenericAPIView):
    permission_classes = [IsCustomer]
    serializer_class = ProductListSerializer

    def get(self, request):
        recent = list(
            RecentlyViewedProduct.objects.filter(user=request.user).select_related("product")[:20]
        )
        queryset = (
            Product.objects.filter(status=ProductStatus.ACTIVE, category__is_active=True)
            .select_related("category", "brand")
            .prefetch_related("images", "variants")
        )
        if recent:
            category_ids = {item.product.category_id for item in recent}
            product_types = {item.product.product_type for item in recent}
            queryset = queryset.filter(
                Q(category_id__in=category_ids) | Q(product_type__in=product_types)
            )
        queryset = queryset.order_by("-is_featured", "-created_at")[:20]
        return response.Response(self.get_serializer(queryset, many=True).data)


def record_product_view(*, user, product):
    if not user.is_authenticated or user.is_staff:
        return
    _, created = RecentlyViewedProduct.objects.get_or_create(user=user, product=product)
    if not created:
        RecentlyViewedProduct.objects.filter(user=user, product=product).update(
            view_count=F("view_count") + 1
        )
