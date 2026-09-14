from django.contrib import admin

from .models import (
    Cart,
    CartItem,
    Coupon,
    Order,
    OrderAddress,
    OrderItem,
    Payment,
    PaymentWebhookEvent,
    Refund,
    ReturnRequest,
    ReturnStatus,
    Shipment,
)
from .tasks import process_return_refund


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "variant_name",
        "sku",
        "unit_price",
        "quantity",
        "line_total",
    )


class OrderAddressInline(admin.TabularInline):
    model = OrderAddress
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "status",
        "total",
        "currency",
        "coupon_code",
        "placed_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("order_number", "user__email", "items__sku")
    readonly_fields = (
        "order_number",
        "idempotency_key",
        "coupon_code",
        "placed_at",
        "updated_at",
    )
    inlines = (OrderItemInline, OrderAddressInline)


admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Coupon)
admin.site.register(Payment)
admin.site.register(PaymentWebhookEvent)
admin.site.register(Shipment)


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "user",
        "reason",
        "quantity",
        "status",
        "requested_at",
    )
    list_filter = ("status", "reason", "requested_at")
    search_fields = ("order__order_number", "user__email", "order_item__sku")
    readonly_fields = ("user", "order", "order_item", "quantity", "requested_at")
    actions = ("approve_and_refund", "reject_returns")

    @admin.action(description="Approve and start Razorpay refund")
    def approve_and_refund(self, request, queryset):
        return_ids = list(
            queryset.filter(status=ReturnStatus.REQUESTED).values_list("pk", flat=True)
        )
        ReturnRequest.objects.filter(pk__in=return_ids).update(status=ReturnStatus.APPROVED)
        for return_id in return_ids:
            process_return_refund.delay(str(return_id))

    @admin.action(description="Reject selected return requests")
    def reject_returns(self, request, queryset):
        queryset.filter(status=ReturnStatus.REQUESTED).update(status=ReturnStatus.REJECTED)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "return_request", "amount", "status", "provider_refund_id")
    list_filter = ("status",)
    search_fields = (
        "return_request__order__order_number",
        "provider_refund_id",
        "payment__provider_payment_id",
    )
    readonly_fields = (
        "return_request",
        "payment",
        "amount",
        "provider_refund_id",
        "idempotency_key",
        "status",
        "failure_reason",
        "created_at",
        "updated_at",
    )
