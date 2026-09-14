from django.core.management.base import BaseCommand

from apps.catalog.models import Category


class Command(BaseCommand):
    help = "Create the standard PASDEDEUX fashion categories."

    categories = (
        ("Clothing", "clothing", 10),
        ("Shoes", "shoes", 20),
        ("Eyewear", "eyewear", 30),
        ("Belts", "belts", 40),
        ("Caps", "caps", 50),
        ("Accessories", "accessories", 60),
    )

    def handle(self, *args, **options):
        created_count = 0
        for name, slug, position in self.categories:
            _, created = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "position": position,
                    "is_active": True,
                },
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(f"Fashion catalog ready ({created_count} categories created).")
        )
