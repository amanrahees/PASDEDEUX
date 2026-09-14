import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class Audience(models.TextChoices):
    EVERYONE = "EVERYONE", "Everyone"
    MEN = "MEN", "Men"
    WOMEN = "WOMEN", "Women"
    KIDS = "KIDS", "Kids"


class ProductType(models.TextChoices):
    CLOTHING = "CLOTHING", "Clothing"
    SHOES = "SHOES", "Shoes"
    EYEWEAR = "EYEWEAR", "Eyewear"
    BELT = "BELT", "Belt"
    CAP = "CAP", "Cap"
    ACCESSORY = "ACCESSORY", "Accessory"


class ProductStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ARCHIVED = "ARCHIVED", "Archived"


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "name")
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    description = models.TextField()
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.EVERYONE,
    )
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    compare_at_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
    )
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["category", "status"]),
            models.Index(fields=["product_type", "audience", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(compare_at_price__isnull=True)
                | Q(compare_at_price__gte=F("base_price")),
                name="compare_price_not_below_base_price",
            )
        ]

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt_text = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "position"],
                name="unique_product_image_position",
            )
        ]

    def __str__(self):
        return f"Image {self.position} for {self.product.name}"


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    color = models.CharField(max_length=80, blank=True)
    size = models.CharField(max_length=40, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    price_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("product", "name")
        indexes = [models.Index(fields=["product", "is_active"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(reserved_quantity__lte=F("stock_quantity")),
                name="reserved_stock_not_above_total_stock",
            ),
            models.UniqueConstraint(
                fields=["product", "name"],
                name="unique_variant_name_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name} ({self.sku})"

    @property
    def price(self):
        return self.price_override if self.price_override is not None else self.product.base_price

    @property
    def available_quantity(self):
        return self.stock_quantity - self.reserved_quantity
