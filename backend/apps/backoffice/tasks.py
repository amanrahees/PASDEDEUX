from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import F

from apps.catalog.models import ProductStatus, ProductVariant


@shared_task
def send_low_stock_notification():
    variants = list(
        ProductVariant.objects.filter(
            is_active=True,
            product__status=ProductStatus.ACTIVE,
        )
        .annotate(available=F("stock_quantity") - F("reserved_quantity"))
        .filter(available__lte=settings.LOW_STOCK_THRESHOLD)
        .select_related("product")
        .order_by("available")[:100]
    )
    if not variants:
        return 0
    recipients = set(settings.LOW_STOCK_NOTIFICATION_EMAILS)
    recipients.update(
        get_user_model()
        .objects.filter(is_superuser=True, is_active=True)
        .values_list("email", flat=True)
    )
    if not recipients:
        return 0
    lines = [
        f"{variant.sku} - {variant.product.name}: {variant.available} available"
        for variant in variants
    ]
    send_mail(
        "PASDEDEUX low-stock alert",
        "The following active variants are low in stock:\n\n" + "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        sorted(recipients),
    )
    return len(variants)
