import hashlib
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.catalog.models import ProductStatus, ProductVariant
from apps.customers.models import Address

from .models import (
    AddressType,
    Cart,
    CartItem,
    Coupon,
    DiscountType,
    Order,
    OrderAddress,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    ReturnRequest,
    ReturnStatus,
)


@transaction.atomic
def add_to_cart(*, user, variant_id, quantity):
    cart, _ = Cart.objects.select_for_update().get_or_create(user=user)
    variant = ProductVariant.objects.select_related("product").get(pk=variant_id)
    if not variant.is_active or variant.product.status != ProductStatus.ACTIVE:
        raise ValidationError("This product variant is unavailable.")
    item, created = CartItem.objects.select_for_update().get_or_create(
        cart=cart, variant=variant, defaults={"quantity": quantity}
    )
    if not created:
        item.quantity += quantity
    if item.quantity > variant.available_quantity:
        raise ValidationError("Requested quantity is not available.")
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def set_cart_item_quantity(*, user, item_id, quantity):
    item = (
        CartItem.objects.select_for_update()
        .select_related("cart", "variant__product")
        .get(pk=item_id, cart__user=user)
    )
    if quantity > item.variant.available_quantity:
        raise ValidationError("Requested quantity is not available.")
    item.quantity = quantity
    item.full_clean()
    item.save(update_fields=["quantity", "updated_at"])
    return item


def _copy_address(order, address, address_type):
    return OrderAddress.objects.create(
        order=order,
        address_type=address_type,
        recipient_name=address.recipient_name,
        phone=address.phone,
        address_line_1=address.address_line_1,
        address_line_2=address.address_line_2,
        city=address.city,
        state=address.state,
        postal_code=address.postal_code,
        country_code=address.country_code,
    )


@transaction.atomic
def _discount_for(coupon, subtotal):
    now = timezone.now()
    if (
        not coupon.is_active
        or not coupon.starts_at <= now < coupon.ends_at
        or subtotal < coupon.minimum_order_value
        or (coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit)
    ):
        raise ValidationError("This coupon is not available.")
    if coupon.discount_type == DiscountType.PERCENTAGE:
        discount = subtotal * coupon.value / Decimal("100")
    else:
        discount = coupon.value
    if coupon.maximum_discount is not None:
        discount = min(discount, coupon.maximum_discount)
    return min(discount, subtotal).quantize(Decimal("0.01"))


@transaction.atomic
def checkout(*, user, shipping_address_id, billing_address_id, idempotency_key, coupon_code=""):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    addresses = Address.objects.filter(
        user=user,
        is_active=True,
        pk__in={shipping_address_id, billing_address_id},
    )
    address_map = {address.pk: address for address in addresses}
    if shipping_address_id not in address_map or billing_address_id not in address_map:
        raise ValidationError("A selected address is invalid.")

    try:
        cart = Cart.objects.select_for_update().get(user=user)
    except Cart.DoesNotExist as error:
        raise ValidationError("The cart is empty.") from error
    items = list(cart.items.select_related("variant__product"))
    if not items:
        raise ValidationError("The cart is empty.")

    variant_ids = [item.variant_id for item in items]
    variants = {
        variant.pk: variant
        for variant in ProductVariant.objects.select_for_update()
        .select_related("product")
        .filter(pk__in=variant_ids)
    }
    subtotal = Decimal("0.00")
    lines = []
    for item in items:
        variant = variants[item.variant_id]
        if (
            not variant.is_active
            or variant.product.status != ProductStatus.ACTIVE
            or item.quantity > variant.available_quantity
        ):
            raise ValidationError(f"Insufficient stock for SKU {variant.sku}.")
        unit_price = variant.price
        line_total = unit_price * item.quantity
        subtotal += line_total
        lines.append((item, variant, unit_price, line_total))

    coupon = None
    discount_total = Decimal("0.00")
    if coupon_code:
        try:
            coupon = Coupon.objects.select_for_update().get(code__iexact=coupon_code.strip())
        except Coupon.DoesNotExist as error:
            raise ValidationError("This coupon is not available.") from error
        discount_total = _discount_for(coupon, subtotal)

    shipping_address = address_map[shipping_address_id]
    if shipping_address.country_code == settings.STORE_COUNTRY_CODE:
        shipping_total = (
            Decimal("0.00")
            if subtotal - discount_total >= settings.DOMESTIC_FREE_SHIPPING_THRESHOLD
            else settings.DOMESTIC_SHIPPING_RATE
        )
    else:
        shipping_total = settings.INTERNATIONAL_SHIPPING_RATE
    total = subtotal - discount_total + shipping_total

    order = Order.objects.create(
        user=user,
        idempotency_key=idempotency_key,
        coupon=coupon,
        coupon_code=coupon.code if coupon else "",
        subtotal=subtotal,
        discount_total=discount_total,
        shipping_total=shipping_total,
        total=total,
        reservation_expires_at=timezone.now()
        + timedelta(minutes=settings.STOCK_RESERVATION_MINUTES),
    )
    _copy_address(order, address_map[shipping_address_id], AddressType.SHIPPING)
    _copy_address(order, address_map[billing_address_id], AddressType.BILLING)

    for item, variant, unit_price, line_total in lines:
        OrderItem.objects.create(
            order=order,
            variant=variant,
            product_name=variant.product.name,
            variant_name=variant.name,
            sku=variant.sku,
            unit_price=unit_price,
            quantity=item.quantity,
            line_total=line_total,
        )
        variant.reserved_quantity = F("reserved_quantity") + item.quantity
        variant.save(update_fields=["reserved_quantity", "updated_at"])

    Payment.objects.create(
        order=order,
        idempotency_key=hashlib.sha256(f"{user.pk}:{idempotency_key}".encode()).hexdigest(),
        amount=order.total,
        currency=order.currency,
    )
    if coupon:
        coupon.times_used = F("times_used") + 1
        coupon.save(update_fields=["times_used", "updated_at"])
    cart.items.all().delete()
    return order, True


@transaction.atomic
def cancel_order(*, order):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status in (OrderStatus.PAID, OrderStatus.PROCESSING):
        if order.shipments.filter(shipped_at__isnull=False).exists():
            raise ValidationError("This order has already shipped and cannot be cancelled.")
        payment = order.payments.filter(status=PaymentStatus.CAPTURED).first()
        if payment is None:
            raise ValidationError("The captured payment could not be found.")
        order.status = OrderStatus.CANCELLATION_PENDING
        order.save(update_fields=["status", "updated_at"])
        from .tasks import process_order_cancellation

        transaction.on_commit(lambda: process_order_cancellation.delay(str(order.pk)))
        return order
    if order.status != OrderStatus.PAYMENT_PENDING:
        raise ValidationError("This order can no longer be cancelled.")
    if order.payments.filter(
        status__in=(PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)
    ).exists():
        raise ValidationError("A payment is already being processed for this order.")
    for item in order.items.select_related("variant"):
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                reserved_quantity=F("reserved_quantity") - item.quantity
            )
    order.status = OrderStatus.CANCELLED
    if order.coupon_id:
        Coupon.objects.filter(pk=order.coupon_id, times_used__gt=0).update(
            times_used=F("times_used") - 1
        )
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def create_return_request(*, user, order_number, order_item_id, quantity, reason, details=""):
    try:
        order = Order.objects.select_for_update().get(order_number=order_number, user=user)
    except Order.DoesNotExist as error:
        raise ValidationError("The selected order does not exist.") from error
    if order.status != OrderStatus.DELIVERED:
        raise ValidationError("Returns are available only after delivery.")

    delivered_at = (
        order.shipments.filter(delivered_at__isnull=False)
        .order_by("-delivered_at")
        .values_list("delivered_at", flat=True)
        .first()
    )
    if delivered_at is None or delivered_at < timezone.now() - timedelta(days=7):
        raise ValidationError("The seven-day return window has closed.")

    try:
        item = order.items.select_for_update().get(pk=order_item_id)
    except OrderItem.DoesNotExist as error:
        raise ValidationError("The selected item does not belong to this order.") from error
    already_requested = (
        item.return_requests.exclude(
            status__in=(ReturnStatus.REJECTED, ReturnStatus.CANCELLED)
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    if quantity + already_requested > item.quantity:
        raise ValidationError("The return quantity exceeds the eligible quantity.")

    return ReturnRequest.objects.create(
        user=user,
        order=order,
        order_item=item,
        quantity=quantity,
        reason=reason,
        details=details,
    )
