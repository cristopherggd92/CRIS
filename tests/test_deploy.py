import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command


@pytest.mark.django_db
def test_crear_admin_crea_una_vez(monkeypatch):
    monkeypatch.setenv("CRIS_ADMIN_USERNAME", "cris")
    monkeypatch.setenv("CRIS_ADMIN_PASSWORD", "UnaClaveLarga123")
    call_command("crear_admin")
    call_command("crear_admin")  # segunda vez no falla ni duplica
    users = get_user_model().objects.filter(username="cris")
    assert users.count() == 1
    assert users.first().is_superuser
    assert users.first().check_password("UnaClaveLarga123")


@pytest.mark.django_db
def test_crear_admin_sin_variables_no_hace_nada(monkeypatch):
    monkeypatch.delenv("CRIS_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("CRIS_ADMIN_PASSWORD", raising=False)
    call_command("crear_admin")
    assert get_user_model().objects.count() == 0
