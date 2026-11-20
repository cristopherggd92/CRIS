from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.finance.services import add_months
from apps.household import services
from apps.household.models import Asset, Bill, Maintenance, Reminder, Service, Vehicle

D = Decimal
FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}
TODAY = timezone.localdate


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="cris", password="clave-segura-123")


@pytest.fixture
def logged(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def luz(user):
    return Service.objects.create(
        owner=user,
        name="Luz",
        kind="luz",
        frequency="bimestral",
        next_due=TODAY() + timedelta(days=3),
        usual_amount=D("650"),
    )


@pytest.fixture
def car(user):
    return Vehicle.objects.create(owner=user, name="Versa", km=50000)


def new(client, kind, data, **extra):
    return client.post(reverse("household:form_new", args=[kind]), data, **extra)


# ---------- Menú y páginas ----------


def test_menu_muestra_hogar(logged):
    html = logged.get(reverse("core:dashboard")).content.decode()
    assert reverse("household:home") in html


@pytest.mark.parametrize(
    "name", ["home", "services", "vehicles", "maintenance", "agenda", "inventory"]
)
def test_paginas_cargan_vacias(logged, name):
    assert logged.get(reverse(f"household:{name}")).status_code == 200


@pytest.mark.parametrize(
    "kind", ["servicio", "recibo", "vehiculo", "mantenimiento", "recordatorio", "articulo"]
)
def test_formulario_en_panel_y_como_pagina(logged, kind):
    partial = logged.get(reverse("household:form_new", args=[kind]), **FETCH)
    assert partial.status_code == 200
    assert "<html" not in partial.content.decode()  # solo el formulario
    page = logged.get(reverse("household:form_new", args=[kind]))
    assert "<html" in page.content.decode()


def test_tipo_inexistente_da_404(logged):
    assert logged.get(reverse("household:form_new", args=["nave"])).status_code == 404


def test_no_veo_datos_de_otro(client, luz):
    otro = get_user_model().objects.create_user(username="otro", password="x-clave-123")
    client.force_login(otro)
    assert client.get(reverse("household:form_edit", args=["servicio", luz.pk])).status_code == 404
    assert client.post(reverse("household:service_pay", args=[luz.pk])).status_code == 404


# ---------- Servicios y recibos ----------


def test_crear_servicio_por_fetch_regresa_json(logged, user):
    response = new(
        logged,
        "servicio",
        {
            "kind": "agua",
            "name": "Agua",
            "frequency": "mensual",
            "next_due": "2026-12-10",
            "usual_amount": "300",
            "is_active": "on",
        },
        **FETCH,
    )
    assert response.json()["ok"] is True
    assert Service.objects.get(owner=user).kind == "agua"


def test_errores_regresan_el_formulario_con_400(logged):
    response = new(logged, "servicio", {"kind": "luz"}, **FETCH)
    assert response.status_code == 400
    assert "hf-error" in response.content.decode()


def test_pagar_recibo_mueve_el_vencimiento(user, luz):
    bill = Bill.objects.create(owner=user, service=luz, amount=D("700"), due_date=luz.next_due)
    old_due = luz.next_due
    bill.pay()
    luz.refresh_from_db()
    assert bill.is_paid
    assert luz.next_due == add_months(old_due, 2)  # bimestral


def test_pagar_en_un_clic_crea_recibo_pagado(logged, luz):
    data = logged.post(
        reverse("household:service_pay", args=[luz.pk]), {"amount": "612.40"}, **FETCH
    ).json()
    bill = luz.bills.get()
    assert bill.is_paid and bill.amount == D("612.40")
    assert "finanzas" in data["finance_url"]
    luz.refresh_from_db()
    assert luz.next_due > TODAY() + timedelta(days=30)


def test_pagar_sin_monto_y_sin_monto_habitual_falla(logged, user):
    s = Service.objects.create(owner=user, name="Gas", next_due=TODAY())
    response = logged.post(reverse("household:service_pay", args=[s.pk]), **FETCH)
    assert response.status_code == 400
    assert not s.bills.exists()


def test_recibo_marcado_como_pagado_desde_el_formulario(logged, luz):
    new(
        logged,
        "recibo",
        {"service": luz.pk, "amount": "650", "due_date": luz.next_due.isoformat(), "paid": "on"},
    )
    assert luz.bills.get().is_paid


def test_recibo_precargado_desde_el_servicio(logged, luz):
    form = logged.get(reverse("household:form_new", args=["recibo"]) + f"?servicio={luz.pk}")
    assert form.context["form"].initial["amount"] == D("650")


# ---------- Vehículos y mantenimiento ----------


def test_vehiculo_crea_recordatorios_automaticos(logged, user):
    new(
        logged,
        "vehiculo",
        {
            "name": "Versa",
            "plate": "abc-123",
            "km": "1000",
            "color": "sky",
            "verification_date": "2027-01-15",
            "insurance_date": "2027-03-01",
        },
    )
    v = Vehicle.objects.get(owner=user)
    assert v.plate == "ABC-123"
    assert set(v.reminders.values_list("category", flat=True)) == {"verificacion", "seguro"}
    assert v.reminders.get(category="verificacion").repeat == "semestral"


def test_mantenimiento_actualiza_kilometraje(logged, car):
    new(
        logged,
        "mantenimiento",
        {
            "area": "auto",
            "vehicle": car.pk,
            "title": "Cambio de aceite",
            "date": TODAY().isoformat(),
            "cost": "950",
            "km": "52000",
            "next_km": "57000",
        },
    )
    car.refresh_from_db()
    assert car.km == 52000
    assert Maintenance.objects.get().km_left == 5000


def test_mantenimiento_de_auto_exige_vehiculo_y_km_coherente(logged, car):
    response = new(
        logged,
        "mantenimiento",
        {
            "area": "auto",
            "title": "Frenos",
            "date": TODAY().isoformat(),
            "cost": "0",
            "km": "50000",
            "next_km": "40000",
        },
        **FETCH,
    )
    assert response.status_code == 400
    html = response.content.decode()
    assert "Elige el vehículo" in html and "Debe ser mayor" in html


def test_mantenimiento_de_casa_ignora_datos_del_auto(logged, user, car):
    new(
        logged,
        "mantenimiento",
        {
            "area": "plomeria",
            "vehicle": car.pk,
            "title": "Fuga",
            "date": TODAY().isoformat(),
            "cost": "400",
            "km": "9",
        },
    )
    m = Maintenance.objects.get(owner=user)
    assert m.vehicle is None and m.km is None and not m.is_car


def test_km_en_linea(logged, car):
    ok = logged.post(reverse("household:vehicle_km", args=[car.pk]), {"km": "61000"}, **FETCH)
    assert ok.json()["ok"]
    bad = logged.post(reverse("household:vehicle_km", args=[car.pk]), {"km": "x"}, **FETCH)
    assert bad.status_code == 400
    car.refresh_from_db()
    assert car.km == 61000


# ---------- Recordatorios ----------


def test_recordatorio_que_se_repite_se_reprograma(logged, user):
    r = Reminder.objects.create(
        owner=user, title="Verificación", due_date=date(2026, 12, 1), repeat="semestral"
    )
    logged.post(reverse("household:reminder_done", args=[r.pk]), **FETCH)
    r.refresh_from_db()
    assert r.due_date == date(2027, 6, 1) and r.done_at is None


def test_recordatorio_unico_queda_completado(logged, user):
    r = Reminder.objects.create(owner=user, title="Licencia", due_date=TODAY(), amount=D("900"))
    data = logged.post(reverse("household:reminder_done", args=[r.pk]), **FETCH).json()
    r.refresh_from_db()
    assert r.done_at == TODAY()
    assert "finance_url" in data


# ---------- Inventario y garantías ----------


def test_estado_de_garantia(user):
    today = TODAY()
    vigente = Asset(owner=user, name="TV", purchase_date=today, warranty_months=12)
    por_vencer = Asset(
        owner=user, name="Licuadora", purchase_date=today - timedelta(days=350), warranty_months=12
    )
    vencida = Asset(owner=user, name="Plancha", purchase_date=date(2020, 1, 1), warranty_months=12)
    sin = Asset(owner=user, name="Silla")
    assert [a.warranty_state for a in (vigente, por_vencer, vencida, sin)] == [
        "active",
        "expiring",
        "expired",
        "",
    ]
    assert vencida.warranty_until == date(2021, 1, 1)


# ---------- Agenda y gastos ----------


def test_agenda_junta_todo_lo_que_vence(user, luz, car):
    Reminder.objects.create(owner=user, title="Seguro", due_date=TODAY() - timedelta(days=2))
    Maintenance.objects.create(
        owner=user, vehicle=car, title="Aceite", date=TODAY(), km=50000, next_km=50500
    )
    Asset.objects.create(
        owner=user, name="Laptop", purchase_date=TODAY() - timedelta(days=355), warranty_months=12
    )
    items = services.agenda(user)
    kinds = {e["kind"] for e in items}
    assert kinds == {"servicio", "recordatorio", "mantenimiento", "garantia"}
    assert items[0]["title"] == "Seguro" and items[0]["state"] == "overdue"
    groups = dict(services.group_agenda(items))
    assert "Vencido" in groups


def test_servicio_con_recibo_pendiente_no_se_duplica_en_agenda(user, luz):
    Bill.objects.create(owner=user, service=luz, amount=D("650"), due_date=luz.next_due)
    kinds = [e["kind"] for e in services.agenda(user)]
    assert kinds == ["recibo"]


def test_solo_cuenta_el_mantenimiento_mas_reciente(user, car):
    Maintenance.objects.create(
        owner=user, vehicle=car, title="Aceite", date=date(2026, 1, 1), next_date=date(2026, 7, 1)
    )
    Maintenance.objects.create(
        owner=user, vehicle=car, title="aceite ", date=date(2026, 7, 2), next_date=date(2027, 1, 2)
    )
    pending = services.pending_maintenance(user)
    assert [m.next_date for m in pending] == [date(2027, 1, 2)]


def test_gastos_por_mes(user, luz, car):
    bill = Bill.objects.create(owner=user, service=luz, amount=D("650"), due_date=TODAY())
    bill.pay()
    Maintenance.objects.create(
        owner=user, vehicle=car, title="Llantas", date=TODAY(), cost=D("4000")
    )
    Maintenance.objects.create(
        owner=user, area="pintura", title="Pintura", date=TODAY(), cost=D("1500")
    )
    current = services.monthly_costs(user)[-1]
    assert (current["servicios"], current["auto"], current["casa"]) == (
        D("650"),
        D("4000"),
        D("1500"),
    )
    assert current["auto_pct"] == pytest.approx(4000 / 6150 * 100)


def test_resumen_muestra_vencidos(logged, user):
    Reminder.objects.create(owner=user, title="Tenencia 2026", due_date=TODAY() - timedelta(days=1))
    html = logged.get(reverse("household:home")).content.decode()
    assert "Tenencia 2026" in html and "Vencido" in html


def test_eliminar_desde_el_panel(logged, luz):
    response = logged.post(reverse("household:delete", args=["servicio", luz.pk]), **FETCH)
    assert response.json()["ok"]
    assert not Service.objects.exists()
