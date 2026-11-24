import importlib

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import clear_url_caches, reverse

import config.urls


@pytest.fixture
def logged(client, db):
    user = get_user_model().objects.create_user(username="cris", password="clave-segura-123")
    client.force_login(user)
    return client


@pytest.fixture
def reload_urls():
    """Vuelve a armar las URLs con la configuración actual y las restaura al final."""

    def _reload():
        clear_url_caches()
        importlib.reload(config.urls)

    yield _reload
    _reload()


@override_settings(DISABLED_MODULES=["shopping", "household"])
def test_modulos_apagados_no_aparecen_ni_responden(logged, reload_urls):
    reload_urls()
    html = logged.get(reverse("core:dashboard")).content.decode()
    assert "Tareas" in html and "Finanzas" in html
    assert "Compras" not in html and "Hogar" not in html
    assert logged.get("/compras/").status_code == 404
    assert logged.get("/hogar/").status_code == 404


def test_sin_modulos_apagados_todo_responde(logged, reload_urls):
    reload_urls()
    html = logged.get(reverse("core:dashboard")).content.decode()
    assert "Compras" in html and "Hogar" in html
    assert logged.get("/compras/").status_code == 200
