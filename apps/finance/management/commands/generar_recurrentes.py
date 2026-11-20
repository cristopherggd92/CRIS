from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.finance.services import generate_due_recurring


class Command(BaseCommand):
    help = "Registra los movimientos recurrentes vencidos de todos los usuarios."

    def handle(self, *args, **options):
        total = sum(generate_due_recurring(u) for u in get_user_model().objects.all())
        self.stdout.write(self.style.SUCCESS(f"{total} movimientos registrados."))
