from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalog.models import ProductVariant
from apps.catalog.serializers import ProductVariantSerializer
from apps.customers.models import Address

from .models import Cart, CartItem, Order, OrderAddress, OrderItem, Payment, Shipment


class CartItemSerializer(serializers.ModelSerializer):
    variant = ProductVariantSerializer(read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ("id", "variant", "quantity", "line_total", "updated_at")

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_line_total(self, item):
        return item.variant.price * item.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ("id", "items", "subtotal", "updated_at")

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_subtotal(self, cart):
        return sum((item.variant.price * item.quantity for item in cart.items.all()), 0)


class AddCartItemSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    quantity = serializers.IntegerField(min_value=1, max_value=20)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=20)


class CheckoutSerializer(serializers.Serializer):
    shipping_address = serializers.PrimaryKeyRelatedField(queryset=Address.objects.none())
    billing_address = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.none(), required=False
    )
    coupon_code = serializers.CharField(max_length=40, allow_blank=True, required=False, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context["request"]
        addresses = Address.objects.none()
        if request.user.is_authenticated:
            addresses = Address.objects.filter(user=request.user, is_active=True)
        self.fields["shipping_address"].queryset = addresses
        self.fields["billing_address"].queryset = addresses

    def validate(self, attrs):
        attrs.setdefault("billing_address", attrs["shipping_address"])
        return attrs


class RazorpayOrderSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=20)


class RazorpayConfirmSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=255)
    razorpay_payment_id = serializers.CharField(max_length=255)
    razorpay_signature = serializers.CharField(max_length=255, write_only=True)


class OrderAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderAddress
        exclude = ("order",)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_name",
            "variant_name",
            "sku",
            "unit_price",
            "quantity",
            "line_total",
        )


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "provider", "amount", "currency", "status", "created_at")


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = (
            "id",
            "carrier",
            "tracking_number",
            "shipped_at",
            "delivered_at",
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    addresses = OrderAddressSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    shipments = ShipmentSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "status",
            "currency",
            "subtotal",
            "discount_total",
            "shipping_total",
            "tax_total",
            "total",
            "coupon_code",
            "reservation_expires_at",
            "customer_note",
            "items",
            "addresses",
            "payments",
            "shipments",
            "placed_at",
            "updated_at",
        )
