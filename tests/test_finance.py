from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.finance import services
from apps.finance.models import (
    Account,
    Category,
    Kind,
    Recurring,
    Transaction,
    ensure_default_categories,
)

D = Decimal


@pytest.fixture
def user(db):
    u = get_user_model().objects.create_user(username="cris", password="clave-segura-123")
    ensure_default_categories(u)
    return u


@pytest.fixture
def logged(client, user, unlock_finance):
    client.force_login(user)
    unlock_finance(client, user)
    return client


@pytest.fixture
def debit(user):
    return Account.objects.create(owner=user, name="Débito", initial_balance=D("1000"))


@pytest.fixture
def card(user):
    return Account.objects.create(
        owner=user, name="Tarjeta", type=Account.Type.CREDIT, initial_balance=D("-500")
    )


def cat(user, name):
    return Category.objects.get(owner=user, name=name)


def tx(user, kind, amount, account, **kw):
    kw.setdefault("date", timezone.localdate())
    return Transaction.objects.create(
        owner=user, kind=kind, amount=D(amount), account=account, **kw
    )


# ---------- Saldos ----------


def test_saldo_con_ingresos_gastos_y_transferencias(user, debit, card):
    tx(user, Kind.INCOME, "2000", debit, category=cat(user, "Salario"))
    tx(user, Kind.EXPENSE, "300.50", debit, category=cat(user, "Comida"))
    tx(user, Kind.TRANSFER, "500", debit, to_account=card)  # pago de tarjeta
    assert debit.balance == D("2199.50")
    assert card.balance == D("0")  # la deuda quedó saldada


def test_categorias_base_se_crean_una_sola_vez(user):
    count = Category.objects.filter(owner=user).count()
    ensure_default_categories(user)
    assert Category.objects.filter(owner=user).count() == count > 0


# ---------- Fechas ----------


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 11, 15), 2, date(2027, 1, 15)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2026, 3, 10), -3, date(2025, 12, 10)),
    ],
)
def test_add_months(start, months, expected):
    assert services.add_months(start, months) == expected


# ---------- Recurrentes ----------


def test_recurrente_mensual_genera_los_meses_atrasados(user, debit):
    today = date(2026, 11, 19)
    rec = Recurring.objects.create(
        owner=user,
        kind=Kind.EXPENSE,
        description="Renta",
        amount=D("8000"),
        account=debit,
        category=cat(user, "Hogar"),
        next_date=date(2026, 9, 1),
    )
    created = services.generate_due_recurring(user, today)
    assert created == 3  # sep, oct, nov
    rec.refresh_from_db()
    assert rec.next_date == date(2026, 12, 1)
    # Llamarla otra vez no duplica
    assert services.generate_due_recurring(user, today) == 0
    assert Transaction.objects.filter(recurring=rec).count() == 3


def test_recurrente_se_desactiva_al_pasar_fecha_fin(user, debit):
    rec = Recurring.objects.create(
        owner=user,
        kind=Kind.EXPENSE,
        description="Curso",
        amount=D("100"),
        account=debit,
        frequency=Recurring.Frequency.WEEKLY,
        next_date=date(2026, 11, 1),
        end_date=date(2026, 11, 10),
    )
    services.generate_due_recurring(user, date(2026, 11, 30))
    rec.refresh_from_db()
    assert Transaction.objects.filter(recurring=rec).count() == 2  # 1 y 8 de nov
    assert rec.is_active is False


def test_recurrente_pausada_no_genera(user, debit):
    Recurring.objects.create(
        owner=user,
        kind=Kind.EXPENSE,
        description="Gym",
        amount=D("500"),
        account=debit,
        next_date=date(2026, 1, 1),
        is_active=False,
    )
    assert services.generate_due_recurring(user, date(2026, 11, 1)) == 0


# ---------- Reportes ----------


def test_gastos_por_categoria_y_totales(user, debit):
    d = date(2026, 11, 5)
    tx(user, Kind.EXPENSE, "300", debit, category=cat(user, "Comida"), date=d)
    tx(user, Kind.EXPENSE, "100", debit, category=cat(user, "Transporte"), date=d)
    tx(user, Kind.INCOME, "1000", debit, category=cat(user, "Salario"), date=d)
    tx(user, Kind.EXPENSE, "999", debit, category=cat(user, "Comida"), date=date(2026, 10, 5))

    rows = services.expenses_by_category(user, 2026, 11)
    assert [(r["name"], r["total"], r["percent"]) for r in rows] == [
        ("Comida", D("300"), D("75.0")),
        ("Transporte", D("100"), D("25.0")),
    ]
    assert rows[-1]["end"] == D("100.00")
    totals = services.month_totals(user, 2026, 11)
    assert totals == {"income": D("1000"), "expense": D("400"), "net": D("600")}


def test_resumen_de_seis_meses_ignora_transferencias(user, debit, card):
    tx(user, Kind.EXPENSE, "200", debit, date=date(2026, 11, 2))
    tx(user, Kind.TRANSFER, "5000", debit, to_account=card, date=date(2026, 11, 2))
    months = services.last_months_summary(user, 2026, 11)
    assert [m["label"] for m in months] == ["Jun", "Jul", "Ago", "Sep", "Oct", "Nov"]
    assert months[-1]["expense"] == D("200")
    assert months[-1]["expense_pct"] == 100


# ---------- Formularios y vistas ----------


def test_registrar_gasto(logged, user, debit):
    response = logged.post(
        reverse("finance:transaction_create"),
        {
            "kind": "gasto",
            "amount": "250.75",
            "date": "2026-11-19",
            "account": debit.pk,
            "category": cat(user, "Comida").pk,
            "description": "Súper",
        },
    )
    assert response.status_code == 302
    assert debit.balance == D("749.25")


def test_transferencia_a_la_misma_cuenta_es_invalida(logged, user, debit):
    response = logged.post(
        reverse("finance:transaction_create"),
        {"kind": "transferencia", "amount": "10", "date": "2026-11-19",
         "account": debit.pk, "to_account": debit.pk},
    )  # fmt: skip
    assert response.status_code == 200
    assert Transaction.objects.count() == 0


def test_categoria_de_otro_tipo_es_invalida(logged, user, debit):
    response = logged.post(
        reverse("finance:transaction_create"),
        {"kind": "gasto", "amount": "10", "date": "2026-11-19",
         "account": debit.pk, "category": cat(user, "Salario").pk},
    )  # fmt: skip
    assert response.status_code == 200
    assert Transaction.objects.count() == 0


def test_no_puedo_usar_cuentas_de_otro_usuario(logged, user, debit):
    otro = get_user_model().objects.create_user(username="otro", password="x" * 12)
    ajena = Account.objects.create(owner=otro, name="Ajena")
    response = logged.post(
        reverse("finance:transaction_create"),
        {"kind": "ingreso", "amount": "10", "date": "2026-11-19", "account": ajena.pk},
    )
    assert response.status_code == 200
    assert Transaction.objects.count() == 0
    assert logged.get(reverse("finance:account_update", args=[ajena.pk])).status_code == 404


def test_borrar_cuenta_con_movimientos_la_archiva(logged, user, debit):
    tx(user, Kind.EXPENSE, "10", debit)
    logged.post(reverse("finance:account_delete", args=[debit.pk]))
    debit.refresh_from_db()
    assert debit.is_archived is True


def test_disponible_para_gastar_descuenta_pagos_proximos(logged, user, debit):
    Recurring.objects.create(
        owner=user,
        kind=Kind.EXPENSE,
        description="Internet",
        amount=D("400"),
        account=debit,
        next_date=timezone.localdate() + timedelta(days=5),
    )
    ctx = logged.get(reverse("finance:home")).context
    assert ctx["total_balance"] == D("1000")
    assert ctx["safe_to_spend"] == D("600")


@pytest.mark.parametrize(
    "name",
    ["home", "transactions", "transaction_create", "accounts", "account_create",
     "recurring", "recurring_create", "categories", "category_create"],
)  # fmt: skip
def test_paginas_cargan(logged, debit, name):
    assert logged.get(reverse(f"finance:{name}")).status_code == 200


def test_tarjeta_finanzas_en_menu_navega(logged):
    html = logged.get(reverse("core:dashboard")).content.decode()
    assert f'href="{reverse("finance:home")}"' in html


def test_listados_con_transferencia_sin_categoria_ni_descripcion(logged, user, debit, card):
    tx(user, Kind.TRANSFER, "100", debit, to_account=card)
    tx(user, Kind.EXPENSE, "50", debit)  # sin categoría ni descripción
    for name in ("finance:transactions", "finance:home"):
        response = logged.get(reverse(name))
        assert response.status_code == 200
        assert 'title="Transferencia"' in response.content.decode()
