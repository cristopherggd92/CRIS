"""Pasos de build en Vercel: aplica migraciones y crea el administrador inicial.

Vercel lo ejecuta después de instalar dependencias (ver [tool.vercel.scripts]
en pyproject.toml). collectstatic lo corre Vercel por su cuenta.
"""

import os
import sys

import django
from django.core.management import call_command


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    if not os.environ.get("DATABASE_URL"):
        sys.exit("Falta DATABASE_URL: conecta una base Postgres al proyecto en Vercel.")
    django.setup()
    call_command("migrate", interactive=False)
    call_command("crear_admin")


if __name__ == "__main__":
    main()
