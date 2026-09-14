import base64
import hashlib
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import F

from apps.catalog.models import ProductVariant

from .models import OrderStatus, Payment, PaymentStatus, PaymentWebhookEvent


class RazorpayError(Exception):
    pass


def _credentials():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ImproperlyConfigured("Razorpay credentials are not configured.")
    return settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET


def _request(path, payload):
    key_id, key_secret = _credentials()
    encoded = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    request = Request(
        f"https://api.razorpay.com/v1/{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Basic {encoded}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            return json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RazorpayError("Razorpay is temporarily unavailable.") from error


@transaction.atomic
def create_razorpay_order(payment):
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    if payment.provider_order_id:
        return payment
    result = _request(
        "orders",
        {
            "amount": int(payment.amount * 100),
            "currency": payment.currency,
            "receipt": payment.order.order_number,
            "notes": {"internal_order_id": str(payment.order_id)},
        },
    )
    payment.provider = "RAZORPAY"
    payment.provider_order_id = result["id"]
    payment.metadata = {"razorpay_order_status": result.get("status")}
    payment.save(update_fields=["provider", "provider_order_id", "metadata", "updated_at"])
    return payment


def verify_payment_signature(*, order_id, payment_id, signature):
    _, secret = _credentials()
    expected = hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(*, raw_body, signature):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise ImproperlyConfigured("Razorpay webhook secret is not configured.")
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@transaction.atomic
def authorize_payment(*, provider_order_id, provider_payment_id):
    payment = Payment.objects.select_for_update().get(provider_order_id=provider_order_id)
    if payment.status == PaymentStatus.CAPTURED:
        return payment
    payment.provider_payment_id = provider_payment_id
    payment.status = PaymentStatus.AUTHORIZED
    payment.save(update_fields=["provider_payment_id", "status", "updated_at"])
    return payment


@transaction.atomic
def capture_payment(*, provider_order_id, provider_payment_id):
    payment = (
        Payment.objects.select_for_update()
        .select_related("order")
        .get(provider_order_id=provider_order_id)
    )
    if payment.status == PaymentStatus.CAPTURED:
        return payment
    order = payment.order
    if order.status != OrderStatus.PAYMENT_PENDING:
        raise ValidationError("The order cannot accept payment in its current state.")
    for item in order.items.select_related("variant"):
        if item.variant_id:
            variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
            if variant.reserved_quantity < item.quantity:
                raise ValidationError("Reserved inventory is inconsistent.")
            variant.stock_quantity = F("stock_quantity") - item.quantity
            variant.reserved_quantity = F("reserved_quantity") - item.quantity
            variant.save(update_fields=["stock_quantity", "reserved_quantity", "updated_at"])
    payment.provider_payment_id = provider_payment_id
    payment.status = PaymentStatus.CAPTURED
    payment.save(update_fields=["provider_payment_id", "status", "updated_at"])
    order.status = OrderStatus.PAID
    order.save(update_fields=["status", "updated_at"])
    return payment


@transaction.atomic
def record_webhook(*, event_id, payload):
    event, created = PaymentWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={"event_type": payload.get("event", "unknown"), "payload": payload},
    )
    return event, created
