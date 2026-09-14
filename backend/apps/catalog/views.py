from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, response, viewsets
from rest_framework.permissions import IsAdminUser

from .models import Brand, Category, Product, ProductImage, ProductStatus, ProductVariant
from .permissions import IsAdminOrReadOnly
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductVariantSerializer,
    ProductWriteSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Category.objects.select_related("parent")
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class BrandViewSet(viewsets.ModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Brand.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ("category__slug", "brand__slug", "product_type", "audience", "is_featured")
    search_fields = ("name", "description", "brand__name", "variants__sku")
    ordering_fields = ("created_at", "base_price", "name")
    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = Product.objects.select_related("category", "brand").prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("position")),
            Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True)),
        )
        if not self.request.user.is_staff:
            queryset = queryset.filter(status=ProductStatus.ACTIVE, category__is_active=True)
        return queryset.distinct()

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ProductWriteSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        from apps.engagement.views import record_product_view

        record_product_view(user=request.user, product=instance)
        return response.Response(self.get_serializer(instance).data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.select_related("product")
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ("product", "product__slug", "is_active", "color", "size")
    search_fields = ("sku", "name", "product__name")


class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.select_related("product")
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ("product", "product__slug")
