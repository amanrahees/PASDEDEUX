import hashlib
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.catalog.models import ProductStatus, ProductVariant
from apps.customers.models import Address

from .models import (
    AddressType,
    Cart,
    CartItem,
    Order,
    OrderAddress,
    OrderItem,
    OrderStatus,
    Payment,
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
def checkout(*, user, shipping_address_id, billing_address_id, idempotency_key):
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

    order = Order.objects.create(
        user=user,
        idempotency_key=idempotency_key,
        subtotal=subtotal,
        total=subtotal,
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
    cart.items.all().delete()
    return order, True


@transaction.atomic
def cancel_order(*, order):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != OrderStatus.PAYMENT_PENDING:
        raise ValidationError("Only unpaid orders can be cancelled by the customer.")
    for item in order.items.select_related("variant"):
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                reserved_quantity=F("reserved_quantity") - item.quantity
            )
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order
