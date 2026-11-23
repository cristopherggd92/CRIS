from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuario de CRIS. Hoy es igual al de Django, pero nos deja
    agregar campos (foto, moneda preferida, etc.) sin romper migraciones."""

    def __str__(self):
        return self.get_full_name() or self.username
