import base64
import hashlib
import hmac
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.catalog.models import ProductVariant

from .models import (
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentWebhookEvent,
    Refund,
    RefundStatus,
    ReturnRequest,
    ReturnStatus,
)


class RazorpayError(Exception):
    pass


def _credentials():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ImproperlyConfigured("Razorpay credentials are not configured.")
    return settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET


def _request(path, payload, extra_headers=None):
    key_id, key_secret = _credentials()
    encoded = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    request = Request(
        f"https://api.razorpay.com/v1/{path}",
        data=json.dumps(payload).encode(),
        headers=headers,
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
    if (
        payment.order.reservation_expires_at
        and payment.order.reservation_expires_at <= timezone.now()
    ):
        raise RazorpayError("The stock reservation has expired.")
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
    payment = (
        Payment.objects.select_for_update()
        .select_related("order")
        .get(provider_order_id=provider_order_id)
    )
    if payment.status == PaymentStatus.CAPTURED:
        return payment
    if payment.order.status != OrderStatus.PAYMENT_PENDING:
        raise ValidationError("The order cannot accept payment in its current state.")
    if (
        payment.order.reservation_expires_at
        and payment.order.reservation_expires_at <= timezone.now()
    ):
        raise ValidationError("The stock reservation has expired.")
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


def refund_return(return_request_id):
    with transaction.atomic():
        return_request = (
            ReturnRequest.objects.select_for_update()
            .select_related("order", "order_item")
            .get(pk=return_request_id)
        )
        if return_request.status == ReturnStatus.REFUNDED:
            return return_request.refund
        if return_request.status not in (
            ReturnStatus.APPROVED,
            ReturnStatus.REFUND_PENDING,
        ):
            raise ValidationError("This return is not approved for a refund.")
        payment = (
            return_request.order.payments.select_for_update()
            .filter(
                status__in=(PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED),
                provider_payment_id__isnull=False,
            )
            .first()
        )
        if payment is None:
            raise ValidationError("No captured payment is available to refund.")

        order = return_request.order
        item = return_request.order_item
        discount_share = Decimal("0.00")
        if order.subtotal:
            discount_share = order.discount_total * item.line_total / order.subtotal
        refundable_line = item.line_total - discount_share
        amount = (refundable_line / item.quantity * return_request.quantity).quantize(
            Decimal("0.01")
        )
        refund, _ = Refund.objects.get_or_create(
            return_request=return_request,
            defaults={
                "payment": payment,
                "amount": amount,
                "idempotency_key": f"return-{return_request.pk}",
            },
        )
        return_request.status = ReturnStatus.REFUND_PENDING
        return_request.save(update_fields=["status", "updated_at"])

    result = _request(
        f"payments/{payment.provider_payment_id}/refund",
        {"amount": int(refund.amount * 100), "notes": {"return_id": str(return_request.pk)}},
        {"X-Razorpay-Idempotency-Key": refund.idempotency_key},
    )
    provider_refund_id = result.get("id")
    if not provider_refund_id:
        raise RazorpayError("Razorpay returned an invalid refund response.")

    with transaction.atomic():
        refund = Refund.objects.select_for_update().select_related("payment").get(pk=refund.pk)
        if refund.status == RefundStatus.PROCESSED:
            return refund
        refund.provider_refund_id = provider_refund_id
        refund.status = RefundStatus.PROCESSED
        refund.failure_reason = ""
        refund.save(
            update_fields=[
                "provider_refund_id",
                "status",
                "failure_reason",
                "updated_at",
            ]
        )
        return_request = ReturnRequest.objects.select_for_update().get(pk=refund.return_request_id)
        return_request.status = ReturnStatus.REFUNDED
        return_request.resolved_at = timezone.now()
        return_request.save(update_fields=["status", "resolved_at", "updated_at"])
        refunded_total = refund.payment.refunds.filter(status=RefundStatus.PROCESSED).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        refund.payment.status = (
            PaymentStatus.REFUNDED
            if refunded_total >= refund.payment.amount
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        refund.payment.save(update_fields=["status", "updated_at"])
        return refund
