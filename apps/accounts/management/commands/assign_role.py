from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Assign a back-office role to a user (and grant Django-admin access for staff roles)"

    def add_arguments(self, parser):
        parser.add_argument("phone")
        parser.add_argument("role", choices=[r.value for r in get_user_model().Role])

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(phone=options["phone"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with phone {options['phone']}") from exc

        user.role = options["role"]
        # Staff roles need is_staff to reach the Django admin; customers must not.
        user.is_staff = user.is_staff_role
        user.save(update_fields=["role", "is_staff"])
        self.stdout.write(
            self.style.SUCCESS(f"{user.phone} is now '{user.role}' (is_staff={user.is_staff})")
        )
