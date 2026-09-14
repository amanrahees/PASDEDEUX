import secrets
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.catalog.models import ProductVariant


def generate_order_number():
    return f"PDD-{secrets.token_hex(6).upper()}"


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.email}"


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="unique_variant_per_cart"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_quantity_gte_one"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.variant.sku}"


class OrderStatus(models.TextChoices):
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
    PAID = "PAID", "Paid"
    PROCESSING = "PROCESSING", "Processing"
    SHIPPED = "SHIPPED", "Shipped"
    DELIVERED = "DELIVERED", "Delivered"
    CANCELLED = "CANCELLED", "Cancelled"
    REFUNDED = "REFUNDED", "Refunded"


class DiscountType(models.TextChoices):
    FIXED = "FIXED", "Fixed amount"
    PERCENTAGE = "PERCENTAGE", "Percentage"


class Coupon(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    discount_type = models.CharField(max_length=12, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    minimum_order_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    maximum_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(blank=True, null=True)
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="coupon_end_after_start"
            ),
            models.CheckConstraint(
                condition=Q(discount_type="FIXED") | Q(value__lte=100),
                name="percentage_coupon_not_above_100",
            ),
        ]

    def __str__(self):
        return self.code


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(
        max_length=20, unique=True, default=generate_order_number, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    idempotency_key = models.CharField(max_length=100)
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        related_name="orders",
        blank=True,
        null=True,
    )
    coupon_code = models.CharField(max_length=40, blank=True)
    status = models.CharField(
        max_length=24, choices=OrderStatus.choices, default=OrderStatus.PAYMENT_PENDING
    )
    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    customer_note = models.TextField(blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    reservation_expires_at = models.DateTimeField(blank=True, null=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-placed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                name="unique_checkout_idempotency_per_user",
            )
        ]
        indexes = [models.Index(fields=["user", "status", "-placed_at"])]

    def __str__(self):
        return self.order_number


class AddressType(models.TextChoices):
    SHIPPING = "SHIPPING", "Shipping"
    BILLING = "BILLING", "Billing"


class OrderAddress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="addresses")
    address_type = models.CharField(max_length=10, choices=AddressType.choices)
    recipient_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=16)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country_code = models.CharField(max_length=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "address_type"], name="unique_address_type_per_order"
            )
        ]

    def __str__(self):
        return f"{self.order.order_number} {self.address_type}"


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        related_name="order_items",
        blank=True,
        null=True,
    )
    product_name = models.CharField(max_length=255)
    variant_name = models.CharField(max_length=160)
    sku = models.CharField(max_length=80)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.sku}"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    AUTHORIZED = "AUTHORIZED", "Authorized"
    CAPTURED = "CAPTURED", "Captured"
    FAILED = "FAILED", "Failed"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially refunded"
    REFUNDED = "REFUNDED", "Refunded"


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=40, default="UNASSIGNED")
    provider_order_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    provider_payment_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    idempotency_key = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order.order_number} {self.status}"


class PaymentWebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=40, default="RAZORPAY")
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-processed_at",)

    def __str__(self):
        return f"{self.provider} {self.event_type} {self.event_id}"


class Shipment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="shipments")
    carrier = models.CharField(max_length=100)
    tracking_number = models.CharField(max_length=150, unique=True)
    shipped_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.tracking_number


class ReturnReason(models.TextChoices):
    WRONG_SIZE = "WRONG_SIZE", "Wrong size"
    DEFECTIVE = "DEFECTIVE", "Defective"
    NOT_AS_DESCRIBED = "NOT_AS_DESCRIBED", "Not as described"
    OTHER = "OTHER", "Other"


class ReturnStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    REFUND_PENDING = "REFUND_PENDING", "Refund pending"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"


class ReturnRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="return_requests",
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="return_requests")
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name="return_requests"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=24, choices=ReturnReason.choices)
    details = models.TextField(max_length=2000, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ReturnStatus.choices,
        default=ReturnStatus.REQUESTED,
        db_index=True,
    )
    admin_note = models.TextField(max_length=2000, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-requested_at",)
        indexes = [models.Index(fields=["order", "status"])]

    def __str__(self):
        return f"Return {self.id} for {self.order.order_number}"

    @property
    def order_number(self):
        return self.order.order_number


class RefundStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"


class Refund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    return_request = models.OneToOneField(
        ReturnRequest, on_delete=models.PROTECT, related_name="refund"
    )
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider_refund_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    idempotency_key = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=12, choices=RefundStatus.choices, default=RefundStatus.PENDING
    )
    failure_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Refund {self.id} ({self.status})"
