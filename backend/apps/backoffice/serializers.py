from rest_framework import serializers

from apps.engagement.models import ReviewStatus
from apps.orders.models import ReturnStatus


class ReturnModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(ReturnStatus.APPROVED, ReturnStatus.REJECTED))
    admin_note = serializers.CharField(max_length=2000, allow_blank=True, required=False)


class ReviewModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(ReviewStatus.APPROVED, ReviewStatus.REJECTED))
