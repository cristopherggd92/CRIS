import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Crea el usuario administrador a partir de CRIS_ADMIN_USERNAME y "
        "CRIS_ADMIN_PASSWORD (y opcional CRIS_ADMIN_EMAIL). Si ya existe, no hace nada."
    )

    def handle(self, *args, **options):
        username = os.environ.get("CRIS_ADMIN_USERNAME")
        password = os.environ.get("CRIS_ADMIN_PASSWORD")
        if not username or not password:
            self.stdout.write("CRIS_ADMIN_USERNAME/CRIS_ADMIN_PASSWORD no definidas: se omite.")
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"El usuario {username} ya existe: no se modifica.")
            return
        User.objects.create_superuser(
            username=username,
            email=os.environ.get("CRIS_ADMIN_EMAIL", ""),
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"Administrador {username} creado."))
