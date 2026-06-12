from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.addresses.models import Address


class Command(BaseCommand):
    help = "Create a test user with a saved address for development"

    def handle(self, *args, **options):
        phone = "+919999999999"
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"name": "Dev User"},
        )

        if created:
            user.set_password("devpass123")
            user.save()
            self.stdout.write(f"Created user: {phone}")
        else:
            self.stdout.write(f"User already exists: {phone}")

        _, addr_created = Address.objects.get_or_create(
            user=user,
            label="home",
            defaults={
                "address_line": "42 Dairy Lane, Andheri West",
                "landmark": "Near Metro Station",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400058",
                "latitude": "19.1364",
                "longitude": "72.8296",
                "is_default": True,
            },
        )
        if addr_created:
            self.stdout.write("  + Home address added")

        self.stdout.write(self.style.SUCCESS(f"\nDev user ready: {phone} / devpass123"))
