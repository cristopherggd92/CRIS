from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.finance import security
from apps.finance.models import Account, FinanceLock, Recurring

ACCOUNT_PASSWORD = "clave-segura-123"
FIN_PASSWORD = "4321"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="cris", password=ACCOUNT_PASSWORD)


@pytest.fixture
def client_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def with_lock(user):
    return security.set_password(user, FIN_PASSWORD)


def test_sin_contrasena_pide_crearla(client_in):
    response = client_in.get(reverse("finance:transactions"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("finance:lock_setup"))
    assert "next=" in response.url


def test_crear_contrasena_guarda_hash_y_desbloquea(client_in, user):
    response = client_in.post(
        reverse("finance:lock_setup"),
        {"password1": FIN_PASSWORD, "password2": FIN_PASSWORD, "next": "/finanzas/movimientos/"},
    )
    assert response.status_code == 302
    assert response.url == "/finanzas/movimientos/"
    lock = FinanceLock.objects.get(owner=user)
    assert lock.password_hash != FIN_PASSWORD  # nunca en texto plano
    assert client_in.get(reverse("finance:home")).status_code == 200


def test_crear_contrasena_valida_coincidencia_y_largo(client_in):
    response = client_in.post(reverse("finance:lock_setup"), {"password1": "12", "password2": "34"})
    assert response.status_code == 200
    assert not FinanceLock.objects.exists()


def test_con_contrasena_pide_desbloquear(client_in, with_lock):
    response = client_in.get(reverse("finance:home"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("finance:unlock"))


def test_desbloqueo_correcto_regresa_a_la_pagina(client_in, with_lock):
    response = client_in.post(
        reverse("finance:unlock"), {"password": FIN_PASSWORD, "next": "/finanzas/cuentas/"}
    )
    assert response.status_code == 302
    assert response.url == "/finanzas/cuentas/"
    assert client_in.get(reverse("finance:accounts")).status_code == 200


def test_next_externo_se_ignora(client_in, with_lock):
    response = client_in.post(
        reverse("finance:unlock"), {"password": FIN_PASSWORD, "next": "https://malo.com/"}
    )
    assert response.url == reverse("finance:home")


def test_desbloqueo_incorrecto_muestra_intentos(client_in, with_lock):
    response = client_in.post(reverse("finance:unlock"), {"password": "0000"})
    assert response.status_code == 200
    assert "Te quedan 4 intentos" in response.content.decode()
    assert client_in.get(reverse("finance:home")).status_code == 302


def test_cinco_fallos_bloquean_aunque_luego_sea_correcta(client_in, with_lock):
    for _ in range(5):
        client_in.post(reverse("finance:unlock"), {"password": "0000"})
    response = client_in.post(reverse("finance:unlock"), {"password": FIN_PASSWORD})
    assert response.status_code == 200
    assert "Demasiados intentos" in response.content.decode()


def test_tras_la_espera_se_puede_desbloquear(client_in, with_lock):
    with_lock.locked_until = timezone.now() - timedelta(seconds=1)
    with_lock.save()
    response = client_in.post(reverse("finance:unlock"), {"password": FIN_PASSWORD})
    assert response.status_code == 302


def test_expira_por_inactividad(client_in, with_lock):
    client_in.post(reverse("finance:unlock"), {"password": FIN_PASSWORD})
    session = client_in.session
    session[security.SESSION_KEY] = timezone.now().timestamp() - 1
    session.save()
    assert client_in.get(reverse("finance:home")).status_code == 302


def test_boton_bloquear(client_in, with_lock):
    client_in.post(reverse("finance:unlock"), {"password": FIN_PASSWORD})
    response = client_in.post(reverse("finance:lock"))
    assert response.url == reverse("core:dashboard")
    assert client_in.get(reverse("finance:home")).status_code == 302


def test_cerrar_sesion_vuelve_a_bloquear(client_in, user, with_lock):
    client_in.post(reverse("finance:unlock"), {"password": FIN_PASSWORD})
    client_in.post(reverse("accounts:logout"))
    client_in.force_login(user)
    assert client_in.get(reverse("finance:home")).status_code == 302


def test_cambiar_con_la_actual(client_in, user, with_lock):
    response = client_in.post(
        reverse("finance:lock_setup"),
        {"current": FIN_PASSWORD, "password1": "nueva1", "password2": "nueva1"},
    )
    assert response.status_code == 302
    assert security.verify(security.get_lock(user), "nueva1")[0]


def test_restablecer_con_contrasena_de_la_cuenta(client_in, user, with_lock):
    response = client_in.post(
        reverse("finance:lock_setup"),
        {"current": ACCOUNT_PASSWORD, "password1": "nueva1", "password2": "nueva1"},
    )
    assert response.status_code == 302
    assert security.verify(security.get_lock(user), "nueva1")[0]


def test_cambiar_con_actual_incorrecta_no_cambia(client_in, user, with_lock):
    response = client_in.post(
        reverse("finance:lock_setup"),
        {"current": "mala", "password1": "nueva1", "password2": "nueva1"},
    )
    assert response.status_code == 200
    assert security.verify(security.get_lock(user), FIN_PASSWORD)[0]


def test_acciones_post_tambien_estan_protegidas(client_in, user, with_lock):
    acc = Account.objects.create(owner=user, name="Débito")
    rec = Recurring.objects.create(
        owner=user,
        kind="gasto",
        amount=10,
        account=acc,
        description="Netflix",
        frequency="mensual",
        next_date=timezone.localdate(),
    )
    response = client_in.post(reverse("finance:recurring_toggle", args=[rec.pk]))
    assert response.status_code == 302
    assert response.url.startswith(reverse("finance:unlock"))
    rec.refresh_from_db()
    assert rec.is_active
    assert client_in.get(reverse("finance:import")).status_code == 302


def test_la_contrasena_es_por_usuario(client, user, with_lock):
    otro = get_user_model().objects.create_user(username="otro", password=ACCOUNT_PASSWORD)
    client.force_login(otro)
    response = client.get(reverse("finance:home"))
    assert response.url.startswith(reverse("finance:lock_setup"))


def test_menu_de_usuario_muestra_enlace(client_in):
    html = client_in.get(reverse("core:dashboard")).content.decode()
    assert "Contraseña de Finanzas" in html
