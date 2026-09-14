import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from ..models import PaymentWebhookEvent
from ..razorpay import verify_payment_signature, verify_webhook_signature


@override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="secret")
def test_payment_signature_verification():
    signature = hmac.new(b"secret", b"order_123|pay_123", hashlib.sha256).hexdigest()
    assert verify_payment_signature(order_id="order_123", payment_id="pay_123", signature=signature)
    assert not verify_payment_signature(
        order_id="order_123", payment_id="pay_123", signature="invalid"
    )


@override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
def test_webhook_signature_uses_raw_body():
    body = b'{"event":"payment.failed"}'
    signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(raw_body=body, signature=signature)


@pytest.mark.django_db
@override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
def test_webhook_is_idempotent():
    payload = {"event": "payment.failed", "payload": {}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
    client = APIClient()

    for _ in range(2):
        response = client.post(
            reverse("razorpay-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
            HTTP_X_RAZORPAY_EVENT_ID="event-001",
        )
        assert response.status_code == 200

    assert PaymentWebhookEvent.objects.count() == 1
