from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ProductVariant


@transaction.atomic
def adjust_stock(*, variant_id, quantity_delta):
    variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    new_quantity = variant.stock_quantity + quantity_delta
    if new_quantity < variant.reserved_quantity:
        raise ValidationError("Stock cannot be reduced below the reserved quantity.")
    variant.stock_quantity = new_quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    return variant
