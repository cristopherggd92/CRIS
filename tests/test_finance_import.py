from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.finance.importers import import_rows, parse_neko_csv
from apps.finance.models import Account, Category, Kind, Recurring, Transaction

# Datos de ejemplo con el mismo formato que exporta NEKO (no son datos reales)
CSV = """Posted Date,Transaction Type,Description,Amount,Account,Category Group,Category,Notes
2026-11-01,Gasto,Súper,-250.50,Nómina,Gastos Básicos,"Supermercado ",
2026-11-01,Pago,Streaming,-199.0,Nómina,Personales,Suscripciones,
2026-11-01,Transferencia,A ahorro,-1000.0,Nómina,,,
2026-11-01,Transferencia,A ahorro,1000.0,Ahorro,,,
2026-11-02,Transferencia,Retiro,-400.0,Nómina,,,
2026-11-02,Transferencia,Retiro,-200.0,Nómina,,,
2026-11-02,Transferencia,Retiro,200.0,Efectivo,,,
2026-11-02,Transferencia,Retiro,400.0,Efectivo,,,
2026-11-03,Transferencia,Huérfana,-50.0,Nómina,,,
2026-11-15,Ingreso,Sueldo,10000.0,Nómina,Trabajo,Sueldo,quincena
2026-11-16,Gasto,Café,-60.0,Efectivo,Personales,Gastos Hormiga,
2026-11-16,Gasto,Café,-60.0,Efectivo,Personales,Gastos Hormiga,
fecha-mala,Gasto,X,-1,Nómina,,,
"""


def upload(text=CSV, name="neko.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="cris", password="clave-segura-123")


@pytest.fixture
def logged(client, user, unlock_finance):
    client.force_login(user)
    unlock_finance(client, user)
    return client


def test_parser_une_transferencias_y_detecta_tipos():
    result = parse_neko_csv(upload())
    kinds = [r.kind for r in result.rows]
    assert kinds.count(Kind.TRANSFER) == 3  # 1 + 2 retiros emparejados por monto
    retiros = sorted((r.amount, r.to_account) for r in result.rows if r.description == "Retiro")
    assert retiros == [("200.0", "Efectivo"), ("400.0", "Efectivo")]
    pago = next(r for r in result.rows if r.description == "Streaming")
    assert pago.kind == Kind.EXPENSE and pago.is_payment
    sueldo = next(r for r in result.rows if r.description.startswith("Sueldo"))
    assert sueldo.kind == Kind.INCOME and sueldo.description == "Sueldo · quincena"
    huerfana = next(r for r in result.rows if r.description == "Huérfana")
    assert huerfana.kind == Kind.EXPENSE and huerfana.warning
    assert len(result.errors) == 1  # la fecha mala


def test_dos_cafes_identicos_tienen_huellas_distintas():
    cafes = [r for r in parse_neko_csv(upload()).rows if r.description == "Café"]
    assert len(cafes) == 2 and cafes[0].ref != cafes[1].ref


def test_columnas_faltantes():
    with pytest.raises(ValueError, match="Faltan columnas"):
        parse_neko_csv(upload("Fecha,Monto\n2026-11-01,10\n"))


def test_importar_crea_cuentas_categorias_y_no_duplica(user):
    summary = import_rows(user, parse_neko_csv(upload()))
    assert summary["created"] == 9
    nomina = Account.objects.get(owner=user, name="Nómina")
    ahorro = Account.objects.get(owner=user, name="Ahorro")
    assert ahorro.type == Account.Type.SAVINGS
    assert Account.objects.get(owner=user, name="Efectivo").type == Account.Type.CASH
    assert Category.objects.filter(owner=user, name="Supermercado", kind=Kind.EXPENSE).exists()
    # 10000 − 250.50 − 199 − 1000 − 400 − 200 − 50
    assert nomina.balance == Decimal("7900.50")
    assert ahorro.balance == Decimal("1000")

    again = import_rows(user, parse_neko_csv(upload()))
    assert again == {"created": 0, "skipped": 9, "recurrings": 0}
    assert Transaction.objects.filter(owner=user).count() == 9


def test_crear_recurrentes_elegidas(user):
    result = parse_neko_csv(upload())
    ref = next(r.ref for r in result.rows if r.description == "Streaming")
    import_rows(user, result, recurring_refs=[ref])
    rec = Recurring.objects.get(owner=user)
    assert rec.description == "Streaming"
    assert rec.amount == Decimal("199.0")
    assert rec.frequency == Recurring.Frequency.MONTHLY


def test_flujo_completo_desde_la_pantalla(logged, user):
    url = reverse("finance:import")
    response = logged.post(url, {"file": upload()})
    assert response.status_code == 302
    preview = logged.get(url)
    assert preview.context["preview"]["to_import"] == 9
    assert "Nómina" in preview.context["preview"]["new_accounts"]
    response = logged.post(url, {"action": "confirm"})
    assert response.status_code == 302
    assert Transaction.objects.filter(owner=user).count() == 9
    assert "finance_import" not in logged.session


def test_rechaza_archivo_que_no_es_csv(logged):
    response = logged.post(reverse("finance:import"), {"file": upload(name="datos.xlsx")})
    assert response.status_code == 200
    assert "Debe ser un archivo .csv" in response.content.decode()


def test_saldo_actual_ajusta_saldo_inicial(logged, user):
    acc = Account.objects.create(owner=user, name="Nómina")
    Transaction.objects.create(
        owner=user, kind=Kind.EXPENSE, amount=Decimal("300"), date="2026-11-01", account=acc
    )
    logged.post(
        reverse("finance:account_update", args=[acc.pk]),
        {"name": "Nómina", "type": "debito", "initial_balance": "0", "color": "slate",
         "current_balance": "5000"},
    )  # fmt: skip
    acc.refresh_from_db()
    assert acc.initial_balance == Decimal("5300")
    assert acc.balance == Decimal("5000")
