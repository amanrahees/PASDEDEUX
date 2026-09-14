from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Brand, Category, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id",
            "parent",
            "name",
            "slug",
            "description",
            "is_active",
            "position",
        )


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "slug", "description", "is_active")


class ProductImageSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), write_only=True)

    class Meta:
        model = ProductImage
        fields = ("id", "product", "image", "alt_text", "position")


class ProductVariantSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), write_only=True)
    stock_quantity = serializers.IntegerField(write_only=True, min_value=0, required=False)
    reserved_quantity = serializers.IntegerField(read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "product",
            "sku",
            "name",
            "color",
            "size",
            "attributes",
            "price_override",
            "price",
            "available_quantity",
            "stock_quantity",
            "reserved_quantity",
            "is_active",
        )


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    minimum_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "category",
            "brand",
            "product_type",
            "audience",
            "base_price",
            "compare_at_price",
            "minimum_price",
            "primary_image",
            "is_featured",
        )

    @extend_schema_field(ProductImageSerializer(allow_null=True))
    def get_primary_image(self, product):
        image = next(iter(product.images.all()), None)
        return ProductImageSerializer(image, context=self.context).data if image else None

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_minimum_price(self, product):
        prices = [variant.price for variant in product.variants.all() if variant.is_active]
        return min(prices, default=product.base_price)


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "category",
            "brand",
            "product_type",
            "audience",
            "base_price",
            "compare_at_price",
            "status",
            "is_featured",
            "images",
            "variants",
            "created_at",
            "updated_at",
        )


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            "id",
            "category",
            "brand",
            "name",
            "slug",
            "description",
            "product_type",
            "audience",
            "base_price",
            "compare_at_price",
            "status",
            "is_featured",
        )
