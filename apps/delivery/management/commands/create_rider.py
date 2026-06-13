from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.delivery.models import DeliveryPartner


class Command(BaseCommand):
    help = "Create a development delivery rider (user + on-duty profile)"

    def add_arguments(self, parser):
        parser.add_argument("--phone", default="+918888888888")
        parser.add_argument("--name", default="Dev Rider")
        parser.add_argument("--vehicle", default="UP78AB1234")

    def handle(self, *args, **options):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            phone=options["phone"], defaults={"name": options["name"]}
        )
        partner, created = DeliveryPartner.objects.get_or_create(
            user=user,
            defaults={"vehicle_number": options["vehicle"], "is_on_duty": True},
        )
        action = "Created" if created else "Exists"
        self.stdout.write(self.style.SUCCESS(f"{action} rider {user.phone} (on_duty={partner.is_on_duty})"))
