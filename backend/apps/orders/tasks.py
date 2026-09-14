from celery import shared_task
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Order, OrderStatus
from .services import cancel_order


@shared_task
def release_expired_reservations():
    order_ids = list(
        Order.objects.filter(
            status=OrderStatus.PAYMENT_PENDING,
            reservation_expires_at__lte=timezone.now(),
        ).values_list("pk", flat=True)
    )
    released = 0
    for order_id in order_ids:
        order = Order.objects.filter(pk=order_id).first()
        if order is None:
            continue
        try:
            cancel_order(order=order)
        except ValidationError:  # pragma: no cover - another worker may win the race
            continue
        released += 1
    return released
