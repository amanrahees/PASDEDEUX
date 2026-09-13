import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q

from .validators import country_code_validator, phone_validator


class ShoppingPreference(models.TextChoices):
    MEN = "men", "Men"
    WOMEN = "women", "Women"
    UNISEX = "unisex", "Unisex"
    NO_PREFERENCE = "none", "No preference"


class AddressLabel(models.TextChoices):
    HOME = "home", "Home"
    WORK = "work", "Work"
    OTHER = "other", "Other"


class CustomerProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile"
    )
    phone = models.CharField(
        max_length=16,
        validators=[phone_validator],
        blank=True,
    )
    avatar = models.ImageField(
        upload_to="customer_avatars/",
        blank=True,
        null=True,
    )
    shopping_preference = models.CharField(
        max_length=10,
        choices=ShoppingPreference.choices,
        default=ShoppingPreference.NO_PREFERENCE,
        help_text="Used only to personalize the storefront.",
    )
    marketing_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "CUSTOMER PROFILES"

    def __str__(self):
        return f"Profile for {self.user.email}"

    def save(self, *args, **kwargs):
        self.phone = self.phone.strip()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"phone"}

        super().save(*args, **kwargs)


class Address(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    label = models.CharField(
        max_length=20,
        choices=AddressLabel.choices,
        default=AddressLabel.HOME,
    )
    recipient_name = models.CharField(max_length=255)
    phone = models.CharField(
        max_length=16,
        validators=[phone_validator],
    )

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country_code = models.CharField(
        max_length=2,
        validators=[country_code_validator],
        help_text="Two-letter ISO country code, such as IN or US.",
    )

    is_default_shipping = models.BooleanField(default=False)
    is_default_billing = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "ADDRESSES"
        ordering = ("-is_default_shipping", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_default_shipping=True),
                name="one_default_shipping_address_per_user",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_default_billing=True),
                name="one_default_billing_address_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.recipient_name} — {self.city}"

    def save(self, *args, **kwargs):
        self.phone = self.phone.strip()
        self.country_code = self.country_code.strip().upper()

        changed_fields = {"phone", "country_code"}

        if not self.is_active:
            self.is_default_shipping = False
            self.is_default_billing = False
            changed_fields.update({"is_default_shipping", "is_default_billing"})

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | changed_fields

        super().save(*args, **kwargs)

    def make_default_shipping(self):
        if self._state.adding:
            raise ValueError("Save the address before making it the default.")

        user_model = self._meta.get_field("user").remote_field.model

        with transaction.atomic():
            user_model.objects.select_for_update().get(pk=self.user_id)

            Address.objects.filter(
                user_id=self.user_id,
                is_default_shipping=True,
            ).exclude(pk=self.pk).update(is_default_shipping=False)

            self.is_active = True
            self.is_default_shipping = True
            self.save(
                update_fields=[
                    "is_active",
                    "is_default_shipping",
                    "updated_at",
                ]
            )

    def make_default_billing(self):
        if self._state.adding:
            raise ValueError("Save the address before making it the default.")

        user_model = self._meta.get_field("user").remote_field.model

        with transaction.atomic():
            user_model.objects.select_for_update().get(pk=self.user_id)

            Address.objects.filter(
                user_id=self.user_id,
                is_default_billing=True,
            ).exclude(pk=self.pk).update(is_default_billing=False)

            self.is_active = True
            self.is_default_billing = True
            self.save(
                update_fields=[
                    "is_active",
                    "is_default_billing",
                    "updated_at",
                ]
            )

    def deactivate(self):
        self.is_active = False
        self.save(
            update_fields=[
                "is_active",
                "is_default_shipping",
                "is_default_billing",
                "updated_at",
            ]
        )
