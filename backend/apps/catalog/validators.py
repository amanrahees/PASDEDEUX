from django.conf import settings
from django.core.exceptions import ValidationError


def validate_product_image_size(image):
    if image.size > settings.MAX_PRODUCT_IMAGE_BYTES:
        maximum_mb = settings.MAX_PRODUCT_IMAGE_BYTES // (1024 * 1024)
        raise ValidationError(f"Product images must not exceed {maximum_mb} MB.")
