from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message="Enter the phone number in E.164 format, for example +919876543210.",
)

country_code_validator = RegexValidator(
    regex=r"^[A-Z]{2}$",
    message="Enter a two-letter uppercase ISO country code, for example IN or US.",
)
