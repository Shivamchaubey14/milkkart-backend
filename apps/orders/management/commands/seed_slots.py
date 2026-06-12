from datetime import date, time, timedelta

from django.core.management.base import BaseCommand

from apps.orders.models import DeliverySlot

SLOTS = [
    (time(6, 0), time(8, 0)),
    (time(8, 0), time(10, 0)),
    (time(17, 0), time(19, 0)),
]


class Command(BaseCommand):
    help = "Seed delivery slots for the next 7 days"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Number of days to generate slots for")

    def handle(self, *args, **options):
        days = options["days"]
        today = date.today()
        created_count = 0

        for i in range(days):
            slot_date = today + timedelta(days=i)
            for start, end in SLOTS:
                _, created = DeliverySlot.objects.get_or_create(
                    date=slot_date,
                    start_time=start,
                    end_time=end,
                    defaults={"capacity": 20},
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"  + {slot_date} {start:%H:%M}-{end:%H:%M}")

        total = DeliverySlot.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\nDone! {created_count} new slots created ({total} total)."))
