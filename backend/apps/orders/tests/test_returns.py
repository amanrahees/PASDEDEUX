from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, ProductType, ProductVariant
from apps.customers.models import CustomerProfile

from ..models import (
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    RefundStatus,
    ReturnReason,
    ReturnRequest,
    ReturnStatus,
    Shipment,
)
from ..razorpay import refund_order_cancellation, refund_return


@pytest.fixture
def delivered_order(db):
    user = get_user_model().objects.create_user(
        email="returner@example.com", password="SafePassword!493", is_active=True
    )
    CustomerProfile.objects.create(user=user)
    category = Category.objects.create(name="Returns", slug="returns-test")
    product = Product.objects.create(
        category=category,
        name="Returnable Shirt",
        slug="returnable-shirt",
        description="A shirt.",
        product_type=ProductType.CLOTHING,
        base_price=Decimal("1000.00"),
        status=ProductStatus.ACTIVE,
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku="RETURN-SHIRT-M",
        name="Medium",
        stock_quantity=10,
    )
    order = Order.objects.create(
        user=user,
        idempotency_key="delivered-order",
        status=OrderStatus.DELIVERED,
        subtotal=Decimal("2000.00"),
        discount_total=Decimal("200.00"),
        total=Decimal("1800.00"),
    )
    item = OrderItem.objects.create(
        order=order,
        variant=variant,
        product_name=product.name,
        variant_name=variant.name,
        sku=variant.sku,
        unit_price=Decimal("1000.00"),
        quantity=2,
        line_total=Decimal("2000.00"),
    )
    Payment.objects.create(
        order=order,
        provider="RAZORPAY",
        provider_order_id="order_return",
        provider_payment_id="pay_return",
        idempotency_key="payment-return",
        amount=order.total,
        currency="INR",
        status=PaymentStatus.CAPTURED,
    )
    Shipment.objects.create(
        order=order,
        carrier="Test",
        tracking_number="TRACK-RETURN",
        delivered_at=timezone.now() - timedelta(days=2),
    )
    client = APIClient()
    client.force_authenticate(user)
    return user, order, item, client


@pytest.mark.django_db
def test_customer_can_request_item_return_within_seven_days(delivered_order):
    user, order, item, client = delivered_order

    response = client.post(
        reverse("returns"),
        {
            "order_number": order.order_number,
            "order_item_id": str(item.pk),
            "quantity": 1,
            "reason": ReturnReason.WRONG_SIZE,
            "details": "Need a different size.",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == ReturnStatus.REQUESTED
    assert ReturnRequest.objects.filter(user=user, order=order).count() == 1


@pytest.mark.django_db
def test_return_quantity_cannot_exceed_ordered_quantity(delivered_order):
    _, order, item, client = delivered_order
    payload = {
        "order_number": order.order_number,
        "order_item_id": str(item.pk),
        "quantity": 2,
        "reason": ReturnReason.DEFECTIVE,
    }
    first = client.post(reverse("returns"), payload, format="json")
    payload["quantity"] = 1
    second = client.post(reverse("returns"), payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 400


@pytest.mark.django_db
def test_return_window_closes_after_seven_days(delivered_order):
    _, order, item, client = delivered_order
    order.shipments.update(delivered_at=timezone.now() - timedelta(days=8))

    response = client.post(
        reverse("returns"),
        {
            "order_number": order.order_number,
            "order_item_id": str(item.pk),
            "quantity": 1,
            "reason": ReturnReason.OTHER,
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_approved_return_creates_idempotent_prorated_refund(delivered_order, monkeypatch):
    user, order, item, _ = delivered_order
    return_request = ReturnRequest.objects.create(
        user=user,
        order=order,
        order_item=item,
        quantity=1,
        reason=ReturnReason.WRONG_SIZE,
        status=ReturnStatus.APPROVED,
    )
    calls = []

    def fake_request(path, payload, extra_headers=None):
        calls.append((path, payload, extra_headers))
        return {"id": "rfnd_test_123"}

    monkeypatch.setattr("apps.orders.razorpay._request", fake_request)

    refund = refund_return(return_request.pk)
    repeated = refund_return(return_request.pk)

    assert refund.pk == repeated.pk
    assert refund.amount == Decimal("900.00")
    assert refund.status == RefundStatus.PROCESSED
    assert calls[0][1]["amount"] == 90000
    assert len(calls) == 1
    return_request.refresh_from_db()
    assert return_request.status == ReturnStatus.REFUNDED


@pytest.mark.django_db(transaction=True)
def test_paid_order_cancellation_refunds_and_restocks(delivered_order, monkeypatch):
    _, order, item, client = delivered_order
    order.status = OrderStatus.PAID
    order.save(update_fields=["status"])
    order.shipments.all().delete()
    variant = item.variant
    variant.stock_quantity = 8
    variant.save(update_fields=["stock_quantity"])
    dispatched = []
    monkeypatch.setattr("apps.orders.tasks.process_order_cancellation.delay", dispatched.append)

    response = client.post(reverse("order-cancel", kwargs={"order_number": order.order_number}))

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.CANCELLATION_PENDING
    assert dispatched == [str(order.pk)]

    monkeypatch.setattr(
        "apps.orders.razorpay._request",
        lambda path, payload, extra_headers=None: {"id": "rfnd_cancel_123"},
    )
    refund = refund_order_cancellation(order.pk)

    order.refresh_from_db()
    variant.refresh_from_db()
    refund.payment.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED
    assert refund.amount == Decimal("1800.00")
    assert refund.payment.status == PaymentStatus.REFUNDED
    assert variant.stock_quantity == 10
