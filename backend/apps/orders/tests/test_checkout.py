from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, ProductType, ProductVariant
from apps.customers.models import Address, CustomerProfile

from ..models import Order, OrderStatus


@pytest.fixture
def customer(db):
    user = get_user_model().objects.create_user(
        email="buyer@example.com",
        password="SafePassword!493",
        is_active=True,
    )
    CustomerProfile.objects.create(user=user)
    return user


@pytest.fixture
def address(customer):
    return Address.objects.create(
        user=customer,
        recipient_name="Buyer",
        phone="+919876543210",
        address_line_1="1 Fashion Street",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400001",
        country_code="IN",
    )


@pytest.fixture
def variant(db):
    category = Category.objects.create(name="Clothing", slug="clothing")
    product = Product.objects.create(
        category=category,
        name="Classic Shirt",
        slug="classic-shirt",
        description="Everyday shirt.",
        product_type=ProductType.CLOTHING,
        base_price=Decimal("1299.00"),
        status=ProductStatus.ACTIVE,
    )
    return ProductVariant.objects.create(
        product=product,
        sku="SHIRT-BLU-M",
        name="Blue / M",
        color="Blue",
        size="M",
        stock_quantity=5,
    )


@pytest.fixture
def client(customer):
    api_client = APIClient()
    api_client.force_authenticate(customer)
    return api_client


@pytest.mark.django_db
def test_cart_and_checkout_reserve_stock(client, customer, address, variant):
    add = client.post(
        reverse("cart-items"),
        {"variant": str(variant.pk), "quantity": 2},
        format="json",
    )
    assert add.status_code == 201

    checkout = client.post(
        reverse("checkout"),
        {"shipping_address": str(address.pk)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-001",
    )
    assert checkout.status_code == 201
    assert checkout.data["total"] == "2598.00"

    order = Order.objects.get(user=customer)
    assert order.items.get().sku == variant.sku
    assert order.addresses.count() == 2
    variant.refresh_from_db()
    assert variant.reserved_quantity == 2


@pytest.mark.django_db
def test_checkout_is_idempotent(client, customer, address, variant):
    client.post(
        reverse("cart-items"),
        {"variant": str(variant.pk), "quantity": 1},
        format="json",
    )
    payload = {"shipping_address": str(address.pk)}
    first = client.post(
        reverse("checkout"), payload, format="json", HTTP_IDEMPOTENCY_KEY="same-key"
    )
    second = client.post(
        reverse("checkout"), payload, format="json", HTTP_IDEMPOTENCY_KEY="same-key"
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["id"] == second.data["id"]
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_customer_cancel_releases_reserved_stock(client, address, variant):
    client.post(
        reverse("cart-items"),
        {"variant": str(variant.pk), "quantity": 2},
        format="json",
    )
    placed = client.post(
        reverse("checkout"),
        {"shipping_address": str(address.pk)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cancel-key",
    )

    cancelled = client.post(
        reverse("order-cancel", kwargs={"order_number": placed.data["order_number"]})
    )

    assert cancelled.status_code == 200
    assert cancelled.data["status"] == OrderStatus.CANCELLED
    variant.refresh_from_db()
    assert variant.reserved_quantity == 0


@pytest.mark.django_db
def test_customer_cannot_checkout_more_than_stock(client, address, variant):
    response = client.post(
        reverse("cart-items"),
        {"variant": str(variant.pk), "quantity": 6},
        format="json",
    )
    assert response.status_code == 400
