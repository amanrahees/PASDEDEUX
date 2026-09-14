from django.contrib import admin

from .models import (
    Cart,
    CartItem,
    Order,
    OrderAddress,
    OrderItem,
    Payment,
    PaymentWebhookEvent,
    Shipment,
)


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
    list_display = ("order_number", "user", "status", "total", "currency", "placed_at")
    list_filter = ("status", "currency")
    search_fields = ("order_number", "user__email", "items__sku")
    readonly_fields = ("order_number", "idempotency_key", "placed_at", "updated_at")
    inlines = (OrderItemInline, OrderAddressInline)


admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Payment)
admin.site.register(PaymentWebhookEvent)
admin.site.register(Shipment)
