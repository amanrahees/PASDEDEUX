from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from ..models import Audience, Category, Product, ProductStatus, ProductType, ProductVariant
from ..services import adjust_stock


@pytest.fixture
def category(db):
    return Category.objects.create(name="Shoes", slug="shoes")


@pytest.fixture
def active_product(category):
    product = Product.objects.create(
        category=category,
        name="Everyday Sneaker",
        slug="everyday-sneaker",
        description="A comfortable everyday sneaker.",
        product_type=ProductType.SHOES,
        audience=Audience.EVERYONE,
        base_price=Decimal("2499.00"),
        status=ProductStatus.ACTIVE,
    )
    ProductVariant.objects.create(
        product=product,
        sku="SHOE-BLK-42",
        name="Black / 42",
        color="Black",
        size="42",
        stock_quantity=10,
    )
    return product


@pytest.mark.django_db
def test_public_catalog_only_lists_active_products(category, active_product):
    Product.objects.create(
        category=category,
        name="Draft Shoe",
        slug="draft-shoe",
        description="Not public.",
        product_type=ProductType.SHOES,
        base_price=Decimal("1000.00"),
        status=ProductStatus.DRAFT,
    )

    response = APIClient().get(reverse("product-list"))

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["slug"] == active_product.slug


@pytest.mark.django_db
def test_anonymous_user_cannot_create_product(category):
    response = APIClient().post(
        reverse("product-list"),
        {
            "category": str(category.pk),
            "name": "Blocked",
            "slug": "blocked",
            "description": "Must not be created.",
            "product_type": ProductType.CLOTHING,
            "audience": Audience.EVERYONE,
            "base_price": "999.00",
            "status": ProductStatus.ACTIVE,
        },
        format="json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_staff_can_create_product(category):
    staff = get_user_model().objects.create_user(
        email="staff@example.com",
        password="SafePassword!493",
        is_active=True,
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(staff)

    response = client.post(
        reverse("product-list"),
        {
            "category": str(category.pk),
            "name": "Classic Belt",
            "slug": "classic-belt",
            "description": "Leather belt.",
            "product_type": ProductType.BELT,
            "audience": Audience.EVERYONE,
            "base_price": "1499.00",
            "status": ProductStatus.ACTIVE,
        },
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_stock_adjustment_cannot_drop_below_reserved(active_product):
    variant = active_product.variants.get()
    variant.reserved_quantity = 8
    variant.save(update_fields=["reserved_quantity"])

    with pytest.raises(ValidationError):
        adjust_stock(variant_id=variant.pk, quantity_delta=-3)
