"""Candado del módulo de Finanzas.

* La primera vez se pide crear una contraseña de Finanzas.
* Después, cada sesión debe desbloquear el módulo con esa contraseña.
* El desbloqueo dura FINANCE_LOCK_MINUTES de inactividad (15 por defecto).
* Tras FINANCE_MAX_ATTEMPTS intentos fallidos se bloquea unos minutos.
"""

from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import FinanceLock

SESSION_KEY = "finance_unlocked_until"


def idle_minutes():
    return getattr(settings, "FINANCE_LOCK_MINUTES", 15)


def max_attempts():
    return getattr(settings, "FINANCE_MAX_ATTEMPTS", 5)


def cooldown_minutes():
    return getattr(settings, "FINANCE_COOLDOWN_MINUTES", 5)


def get_lock(user):
    return FinanceLock.objects.filter(owner=user).first()


def set_password(user, raw):
    lock, _ = FinanceLock.objects.get_or_create(owner=user, defaults={"password_hash": ""})
    lock.password_hash = make_password(raw)
    lock.failed_attempts = 0
    lock.locked_until = None
    lock.save()
    return lock


def is_unlocked(request):
    until = request.session.get(SESSION_KEY)
    return bool(until) and until > timezone.now().timestamp()


def unlock(request):
    request.session[SESSION_KEY] = (timezone.now() + timedelta(minutes=idle_minutes())).timestamp()


def touch(request):
    """Cada visita al módulo renueva el tiempo de inactividad."""
    unlock(request)


def lock(request):
    request.session.pop(SESSION_KEY, None)


def remaining_cooldown(lock_obj):
    if lock_obj.locked_until and lock_obj.locked_until > timezone.now():
        return int((lock_obj.locked_until - timezone.now()).total_seconds() // 60) + 1
    return 0


def verify(lock_obj, raw):
    """Valida la contraseña y lleva la cuenta de intentos fallidos.

    Regresa (ok, mensaje_de_error).
    """
    wait = remaining_cooldown(lock_obj)
    if wait:
        return False, f"Demasiados intentos. Intenta de nuevo en {wait} min."
    if check_password(raw, lock_obj.password_hash):
        lock_obj.failed_attempts = 0
        lock_obj.locked_until = None
        lock_obj.save(update_fields=["failed_attempts", "locked_until"])
        return True, ""
    lock_obj.failed_attempts += 1
    if lock_obj.failed_attempts >= max_attempts():
        lock_obj.failed_attempts = 0
        lock_obj.locked_until = timezone.now() + timedelta(minutes=cooldown_minutes())
        lock_obj.save(update_fields=["failed_attempts", "locked_until"])
        return False, f"Demasiados intentos. Intenta de nuevo en {cooldown_minutes()} min."
    lock_obj.save(update_fields=["failed_attempts"])
    left = max_attempts() - lock_obj.failed_attempts
    return False, f"Contraseña incorrecta. Te quedan {left} intento{'s' if left != 1 else ''}."


def guard(request):
    """Regresa un redirect si el módulo está bloqueado, o None si puede pasar."""
    if not request.user.is_authenticated:
        return None  # LoginRequiredMiddleware se encarga
    if not get_lock(request.user):
        return redirect(
            f"{reverse('finance:lock_setup')}?{urlencode({'next': request.get_full_path()})}"
        )
    if not is_unlocked(request):
        return redirect(
            f"{reverse('finance:unlock')}?{urlencode({'next': request.get_full_path()})}"
        )
    touch(request)
    return None


def finance_unlock_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        return guard(request) or view(request, *args, **kwargs)

    return wrapper
