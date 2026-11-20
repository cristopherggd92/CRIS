import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


def test_health_es_publico(client):
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_usuario_personalizado():
    User = get_user_model()
    assert User._meta.label == "accounts.User"
    user = User.objects.create_user(username="cris", password="clave-segura-123")
    assert user.check_password("clave-segura-123")
