from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # pruebas rápidas

# Las pruebas siempre usan SQLite, aunque exista DATABASE_URL en el .env.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Las pruebas cubren todos los módulos, aunque estén apagados en tu PC o en producción.
DISABLED_MODULES = []
