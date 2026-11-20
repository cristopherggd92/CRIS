"""Cálculos del módulo Hogar: agenda de vencimientos y gastos por mes."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from apps.finance.services import MONTHS_ES, add_months

from .models import Asset, Bill, Maintenance, Reminder, Service, due_state

HORIZON_DAYS = 60
KM_WARNING = 1000


def _entry(**kw):
    kw.setdefault("amount", None)
    kw.setdefault("action", None)
    kw.setdefault("edit", None)
    kw["state"] = kw.get("state") or due_state(kw["date"])
    return kw


def agenda(user, horizon=HORIZON_DAYS):
    """Todo lo que vence pronto (o ya venció), ordenado por fecha."""
    today = timezone.localdate()
    limit = today + timedelta(days=horizon)
    items = []

    unpaid = Bill.objects.filter(owner=user, paid_at__isnull=True, due_date__lte=limit)
    with_bill = set()
    for bill in unpaid.select_related("service"):
        with_bill.add(bill.service_id)
        items.append(
            _entry(
                kind="recibo",
                date=bill.due_date,
                title=f"Recibo de {bill.service.name}",
                subtitle=bill.period or bill.service.provider,
                icon=bill.service.icon,
                amount=bill.amount,
                action={"label": "Pagar", "url": reverse("household:bill_pay", args=[bill.pk])},
                edit=reverse("household:form_edit", args=["recibo", bill.pk]),
            )
        )

    services = Service.objects.filter(owner=user, is_active=True, next_due__lte=limit)
    for s in services.exclude(pk__in=with_bill):
        items.append(
            _entry(
                kind="servicio",
                date=s.next_due,
                title=s.name,
                subtitle=f"{s.get_frequency_display()} · {s.provider}".strip(" ·"),
                icon=s.icon,
                amount=s.usual_amount,
                action={"label": "Pagar", "url": reverse("household:service_pay", args=[s.pk])},
                edit=reverse("household:form_edit", args=["servicio", s.pk]),
            )
        )

    reminders = Reminder.objects.filter(owner=user, done_at__isnull=True, due_date__lte=limit)
    for r in reminders.select_related("vehicle"):
        items.append(
            _entry(
                kind="recordatorio",
                date=r.due_date,
                title=r.title,
                subtitle=" · ".join(
                    x for x in (r.get_category_display(), r.vehicle and r.vehicle.name) if x
                ),
                icon=r.icon,
                amount=r.amount,
                action={"label": "Hecho", "url": reverse("household:reminder_done", args=[r.pk])},
                edit=reverse("household:form_edit", args=["recordatorio", r.pk]),
            )
        )

    for m in pending_maintenance(user):
        km_left = m.km_left
        by_km = km_left is not None and km_left <= KM_WARNING
        if not (by_km or (m.next_date and m.next_date <= limit)):
            continue
        when = m.next_date if m.next_date and not by_km else min(m.next_date or today, today)
        subtitle = m.vehicle.name if m.vehicle else m.get_area_display()
        if km_left is not None:
            subtitle += f" · faltan {km_left:,} km" if km_left > 0 else " · ya pasó el km"
        items.append(
            _entry(
                kind="mantenimiento",
                date=when,
                state="overdue" if km_left is not None and km_left <= 0 else None,
                title=m.title,
                subtitle=subtitle,
                icon="car" if m.vehicle_id else "wrench",
                action={
                    "label": "Registrar",
                    "url": reverse("household:form_new", args=["mantenimiento"])
                    + f"?repetir={m.pk}",
                    "drawer": True,
                },
                edit=reverse("household:form_edit", args=["mantenimiento", m.pk]),
            )
        )

    for a in Asset.objects.filter(owner=user, warranty_months__gt=0, purchase_date__isnull=False):
        until = a.warranty_until
        if today <= until <= today + timedelta(days=30):
            items.append(
                _entry(
                    kind="garantia",
                    date=until,
                    state="soon",
                    title=f"Garantía de {a.name}",
                    subtitle="Revisa que funcione bien antes de que venza",
                    icon="shield",
                    edit=reverse("household:form_edit", args=["articulo", a.pk]),
                )
            )

    items.sort(key=lambda e: (e["date"], e["title"]))
    return items


def pending_maintenance(user):
    """El mantenimiento más reciente de cada tipo que tenga un 'próximo servicio'."""
    seen, result = set(), []
    qs = Maintenance.objects.filter(owner=user).select_related("vehicle").order_by("-date", "-id")
    for m in qs:
        key = (m.vehicle_id, m.area, m.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        if m.next_date or m.next_km:
            result.append(m)
    return result


def group_agenda(items):
    today = timezone.localdate()
    groups = {"Vencido": [], "Esta semana": [], "Próximas semanas": []}
    for e in items:
        if e["state"] == "overdue":
            groups["Vencido"].append(e)
        elif e["date"] <= today + timedelta(days=7):
            groups["Esta semana"].append(e)
        else:
            groups["Próximas semanas"].append(e)
    return [(label, rows) for label, rows in groups.items() if rows]


def monthly_costs(user, months=6):
    """Gasto por mes: servicios pagados, auto y casa."""
    today = timezone.localdate()
    start = add_months(today.replace(day=1), -(months - 1))
    data = defaultdict(
        lambda: {"servicios": Decimal("0"), "auto": Decimal("0"), "casa": Decimal("0")}
    )

    bills = (
        Bill.objects.filter(owner=user, paid_at__gte=start)
        .annotate(m=TruncMonth("paid_at"))
        .values("m")
        .annotate(total=Sum("amount"))
    )
    for row in bills:
        data[row["m"]]["servicios"] += row["total"]

    maint = (
        Maintenance.objects.filter(owner=user, date__gte=start)
        .annotate(m=TruncMonth("date"))
        .values("m", "area")
        .annotate(total=Sum("cost"))
    )
    for row in maint:
        bucket = "auto" if row["area"] == Maintenance.Area.CAR else "casa"
        data[row["m"]][bucket] += row["total"]

    result = []
    for i in range(months):
        first = add_months(start, i)
        values = data.get(
            first, {"servicios": Decimal("0"), "auto": Decimal("0"), "casa": Decimal("0")}
        )
        total = sum(values.values())
        result.append({"key": first, "label": MONTHS_ES[first.month - 1], "total": total, **values})
    top = max((r["total"] for r in result), default=0) or 1
    for r in result:
        for k in ("servicios", "auto", "casa"):
            r[f"{k}_pct"] = float(r[k] / top * 100)
    return result
