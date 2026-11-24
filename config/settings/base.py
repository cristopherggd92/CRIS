import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

# En Vercel se agregan solos los dominios del despliegue (variables de sistema de Vercel).
for _var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    _host = os.getenv(_var)
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

# Orígenes de confianza para formularios (CSRF) cuando se sirve por HTTPS.
_LOCAL_HOSTS = ("localhost", "127.0.0.1")
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in _LOCAL_HOSTS]
CSRF_TRUSTED_ORIGINS += [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps de CRIS
    "apps.accounts",
    "apps.core",
    "apps.tasks",
    "apps.finance",
    "apps.shopping",
    "apps.household",
]

# Módulos apagados: no aparecen en el menú y sus URLs no existen (dan 404).
# Sus apps siguen instaladas para conservar las tablas y los datos.
# Para volver a activarlos, quítalos de aquí o define CRIS_DISABLED_MODULES en el .env
# (vacío = todos activos). Valores posibles: tasks, finance, shopping, household.
DISABLED_MODULES = [
    m.strip()
    for m in os.getenv("CRIS_DISABLED_MODULES", "shopping,household").split(",")
    if m.strip()
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Con DATABASE_URL (Postgres en producción) se usa esa base; sin ella, SQLite local.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
        # Neon usa un pooler (PgBouncer) en modo transacción.
        disable_server_side_cursors=True,
    )
}

# Usuario personalizado: debe existir ANTES de la primera migración
AUTH_USER_MODEL = "accounts.User"

# Login
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # "Recordarme": 14 días

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
