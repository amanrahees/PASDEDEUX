from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, ProductType, ProductVariant
from apps.customers.models import CustomerProfile
from apps.engagement.models import ProductReview, ReviewStatus
from apps.orders.models import (
    Order,
    OrderItem,
    OrderStatus,
    ReturnReason,
    ReturnRequest,
    ReturnStatus,
    Shipment,
)


@pytest.fixture
def store_data(db):
    customer = get_user_model().objects.create_user(
        email="dashboard-customer@example.com",
        password="SafePassword!493",
        is_active=True,
    )
    CustomerProfile.objects.create(user=customer)
    category = Category.objects.create(name="Dashboard", slug="dashboard-test")
    product = Product.objects.create(
        category=category,
        name="Low Stock Cap",
        slug="low-stock-cap",
        description="A cap.",
        product_type=ProductType.CAP,
        base_price=Decimal("500.00"),
        status=ProductStatus.ACTIVE,
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku="LOW-CAP",
        name="Standard",
        stock_quantity=3,
    )
    order = Order.objects.create(
        user=customer,
        idempotency_key="dashboard-order",
        status=OrderStatus.PAID,
        subtotal=Decimal("500.00"),
        total=Decimal("500.00"),
    )
    item = OrderItem.objects.create(
        order=order,
        variant=variant,
        product_name=product.name,
        variant_name=variant.name,
        sku=variant.sku,
        unit_price=Decimal("500.00"),
        quantity=1,
        line_total=Decimal("500.00"),
    )
    return customer, product, variant, order, item


@pytest.fixture
def admin_client(db):
    admin = get_user_model().objects.create_superuser(
        email="owner@example.com", password="SafePassword!493"
    )
    client = APIClient()
    client.force_authenticate(admin)
    return client


@pytest.mark.django_db
def test_dashboard_and_low_stock_are_superuser_only(admin_client, store_data):
    customer, _, variant, _, _ = store_data
    dashboard = admin_client.get(reverse("backoffice-dashboard"))
    low_stock = admin_client.get(reverse("backoffice-low-stock"))
    customer_client = APIClient()
    customer_client.force_authenticate(customer)
    denied = customer_client.get(reverse("backoffice-dashboard"))

    assert dashboard.status_code == 200
    assert dashboard.data["orders"] == 1
    assert dashboard.data["gross_sales"] == Decimal("500.00")
    assert low_stock.data[0]["sku"] == variant.sku
    assert denied.status_code == 403


@pytest.mark.django_db
def test_superuser_can_moderate_review(admin_client, store_data):
    customer, product, _, _, _ = store_data
    review = ProductReview.objects.create(
        user=customer,
        product=product,
        rating=4,
        body="Good product.",
    )

    response = admin_client.post(
        reverse("backoffice-review-moderate", kwargs={"pk": review.pk}),
        {"status": ReviewStatus.APPROVED},
        format="json",
    )

    review.refresh_from_db()
    assert response.status_code == 200
    assert review.status == ReviewStatus.APPROVED


@pytest.mark.django_db(transaction=True)
def test_approved_return_dispatches_refund_job(monkeypatch, store_data):
    customer, _, _, order, item = store_data
    admin = get_user_model().objects.create_superuser(
        email="refund-admin@example.com", password="SafePassword!493"
    )
    client = APIClient()
    client.force_authenticate(admin)
    return_request = ReturnRequest.objects.create(
        user=customer,
        order=order,
        order_item=item,
        quantity=1,
        reason=ReturnReason.DEFECTIVE,
    )
    dispatched = []
    monkeypatch.setattr("apps.backoffice.views.process_return_refund.delay", dispatched.append)

    response = client.post(
        reverse("backoffice-return-moderate", kwargs={"pk": return_request.pk}),
        {"status": ReturnStatus.APPROVED, "admin_note": "Approved after inspection."},
        format="json",
    )

    return_request.refresh_from_db()
    assert response.status_code == 200
    assert return_request.status == ReturnStatus.APPROVED
    assert dispatched == [str(return_request.pk)]


@pytest.mark.django_db
def test_superuser_can_progress_order_through_fulfillment(admin_client, store_data):
    _, _, _, order, _ = store_data
    url = reverse("backoffice-fulfillment", kwargs={"order_number": order.order_number})

    processing = admin_client.post(url, {"status": OrderStatus.PROCESSING}, format="json")
    shipped = admin_client.post(
        url,
        {
            "status": OrderStatus.SHIPPED,
            "carrier": "DHL",
            "tracking_number": "DHL-TRACK-001",
        },
        format="json",
    )
    delivered = admin_client.post(url, {"status": OrderStatus.DELIVERED}, format="json")

    order.refresh_from_db()
    shipment = Shipment.objects.get(order=order)
    assert processing.status_code == 200
    assert shipped.status_code == 200
    assert delivered.status_code == 200
    assert order.status == OrderStatus.DELIVERED
    assert shipment.shipped_at is not None
    assert shipment.delivered_at is not None


@pytest.mark.django_db
def test_fulfillment_cannot_skip_statuses(admin_client, store_data):
    _, _, _, order, _ = store_data

    response = admin_client.post(
        reverse("backoffice-fulfillment", kwargs={"order_number": order.order_number}),
        {
            "status": OrderStatus.SHIPPED,
            "carrier": "DHL",
            "tracking_number": "DHL-TRACK-SKIP",
        },
        format="json",
    )

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID
