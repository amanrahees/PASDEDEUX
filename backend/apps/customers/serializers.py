from rest_framework import serializers

from .models import Address, CustomerProfile


class CustomerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = (
            "id",
            "email",
            "phone",
            "avatar",
            "shopping_preference",
            "marketing_opt_in",
            "updated_at",
        )
        read_only_fields = ("id", "email", "updated_at")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "recipient_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country_code",
            "is_default_shipping",
            "is_default_billing",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "is_default_shipping",
            "is_default_billing",
            "created_at",
            "updated_at",
        )
