import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

PASSWORD = "clave-segura-123"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="cris", password=PASSWORD)


@pytest.mark.django_db
def test_login_muestra_formulario(client):
    response = client.get(reverse("accounts:login"))
    html = response.content.decode()
    assert response.status_code == 200
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert "Iniciar sesión" in html


@pytest.mark.django_db
def test_anonimo_es_redirigido_al_login(client):
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_login_correcto_lleva_al_menu(client, user):
    response = client.post(
        reverse("accounts:login"), {"username": "cris", "password": PASSWORD}, follow=True
    )
    assert response.redirect_chain[-1][0] == reverse("core:dashboard")
    assert "Tareas" in response.content.decode()


def test_login_incorrecto_muestra_error(client, user):
    response = client.post(reverse("accounts:login"), {"username": "cris", "password": "mala"})
    assert response.status_code == 200
    assert "Usuario o contraseña incorrectos" in response.content.decode()


def test_sin_recordarme_la_sesion_expira_al_cerrar_navegador(client, user):
    client.post(reverse("accounts:login"), {"username": "cris", "password": PASSWORD})
    assert client.session.get_expire_at_browser_close() is True


def test_con_recordarme_la_sesion_persiste(client, user):
    client.post(
        reverse("accounts:login"),
        {"username": "cris", "password": PASSWORD, "remember_me": "on"},
    )
    assert client.session.get_expire_at_browser_close() is False


def test_usuario_logueado_no_ve_el_login(client, user):
    client.force_login(user)
    response = client.get(reverse("accounts:login"))
    assert response.status_code == 302


def test_logout_cierra_sesion(client, user):
    client.force_login(user)
    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert response.url == reverse("accounts:login")
    assert client.get(reverse("core:dashboard")).status_code == 302


def test_menu_muestra_los_modulos(client, user):
    client.force_login(user)
    html = client.get(reverse("core:dashboard")).content.decode()
    for nombre in ("Tareas", "Finanzas", "Notas", "Hábitos"):
        assert nombre in html
    assert "Próximamente" in html