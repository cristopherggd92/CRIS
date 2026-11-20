import pytest

FINANCE_PASSWORD = "1234"


@pytest.fixture
def unlock_finance():
    """Crea la contraseña de Finanzas y deja el módulo desbloqueado en la sesión del cliente."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.finance import security

    def _unlock(client, user):
        security.set_password(user, FINANCE_PASSWORD)
        session = client.session
        session[security.SESSION_KEY] = (timezone.now() + timedelta(minutes=15)).timestamp()
        session.save()

    return _unlock
