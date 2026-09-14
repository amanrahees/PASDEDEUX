from rest_framework import serializers

from apps.engagement.models import ReviewStatus
from apps.orders.models import OrderStatus, ReturnStatus
from apps.orders.serializers import OrderSerializer


class ReturnModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(ReturnStatus.APPROVED, ReturnStatus.REJECTED))
    admin_note = serializers.CharField(max_length=2000, allow_blank=True, required=False)


class ReviewModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(ReviewStatus.APPROVED, ReviewStatus.REJECTED))


class FulfillmentSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED)
    )
    carrier = serializers.CharField(max_length=100, required=False)
    tracking_number = serializers.CharField(max_length=150, required=False)

    def validate(self, attrs):
        if attrs["status"] == OrderStatus.SHIPPED and (
            not attrs.get("carrier") or not attrs.get("tracking_number")
        ):
            raise serializers.ValidationError(
                "Carrier and tracking number are required when shipping an order."
            )
        return attrs


class BackofficeOrderSerializer(OrderSerializer):
    customer_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ("customer_email",)
