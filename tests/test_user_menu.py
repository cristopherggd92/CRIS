import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

PASSWORD = "clave-segura-123"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="cris", password=PASSWORD, email="cris@example.com"
    )


def test_header_muestra_logo_y_menu(client, user):
    client.force_login(user)
    html = client.get(reverse("core:dashboard")).content.decode()
    assert "img/cris-logo.png" in html
    assert "Cambiar contraseña" in html
    assert "Cerrar sesión" in html
    assert "cris@example.com" in html
    assert reverse("admin:index") not in html  # no es staff


def test_staff_ve_administracion(client, user):
    user.is_staff = True
    user.save()
    client.force_login(user)
    html = client.get(reverse("core:dashboard")).content.decode()
    assert reverse("admin:index") in html


def test_cambiar_contrasena(client, user):
    client.force_login(user)
    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": PASSWORD,
            "new_password1": "otra-clave-larga-456",
            "new_password2": "otra-clave-larga-456",
        },
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("otra-clave-larga-456")
    # La sesión sigue abierta
    assert client.get(reverse("core:dashboard")).status_code == 200


def test_cambiar_contrasena_con_actual_incorrecta(client, user):
    client.force_login(user)
    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "mala",
            "new_password1": "otra-clave-larga-456",
            "new_password2": "otra-clave-larga-456",
        },
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(PASSWORD)
