"""Lógica de negocio de Finanzas: fechas, recurrentes y reportes."""

import calendar
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Kind, Recurring, Transaction

MONTHS_ES = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]  # fmt: skip
MONTHS_ES_LONG = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_period(d: date, frequency: str) -> date:
    if frequency == Recurring.Frequency.WEEKLY:
        return d + timedelta(days=7)
    if frequency == Recurring.Frequency.BIWEEKLY:
        return d + timedelta(days=15)
    if frequency == Recurring.Frequency.YEARLY:
        return add_months(d, 12)
    return add_months(d, 1)


def month_bounds(year: int, month: int):
    first = date(year, month, 1)
    return first, add_months(first, 1)


def parse_month(value: str | None):
    """'2026-11' -> (2026, 11). Si no es válido, regresa el mes actual."""
    today = timezone.localdate()
    try:
        year, month = (int(x) for x in (value or "").split("-"))
        date(year, month, 1)
        return year, month
    except (ValueError, TypeError):
        return today.year, today.month


MAX_RUNS = 400  # límite de seguridad por si una recurrente quedó muy atrasada


def generate_due_recurring(user, today: date | None = None) -> int:
    """Registra los movimientos de las recurrentes cuya fecha ya llegó.

    Se llama al abrir el módulo, así que no necesitas un cron. Es seguro
    llamarla varias veces: cada ejecución avanza ``next_date``.
    """
    today = today or timezone.localdate()
    created = 0
    with transaction.atomic():
        due = Recurring.objects.select_for_update().filter(
            owner=user, is_active=True, next_date__lte=today
        )
        for rec in due:
            runs = 0
            while rec.next_date <= today and runs < MAX_RUNS:
                if rec.end_date and rec.next_date > rec.end_date:
                    rec.is_active = False
                    break
                Transaction.objects.create(
                    owner=user,
                    kind=rec.kind,
                    amount=rec.amount,
                    date=rec.next_date,
                    account=rec.account,
                    to_account=rec.to_account if rec.kind == Kind.TRANSFER else None,
                    category=rec.category if rec.kind != Kind.TRANSFER else None,
                    description=rec.description,
                    recurring=rec,
                )
                created += 1
                runs += 1
                rec.next_date = add_period(rec.next_date, rec.frequency)
            if rec.end_date and rec.next_date > rec.end_date:
                rec.is_active = False
            rec.save(update_fields=["next_date", "is_active"])
    return created


def month_totals(user, year: int, month: int):
    start, end = month_bounds(year, month)
    sums = Transaction.objects.filter(owner=user, date__gte=start, date__lt=end).aggregate(
        income=Sum("amount", filter=Q(kind=Kind.INCOME)),
        expense=Sum("amount", filter=Q(kind=Kind.EXPENSE)),
    )
    income = sums["income"] or Decimal("0")
    expense = sums["expense"] or Decimal("0")
    return {"income": income, "expense": expense, "net": income - expense}


def expenses_by_category(user, year: int, month: int):
    """Lista [{name, color, total, percent, start, end}] para la gráfica de dona."""
    start, end = month_bounds(year, month)
    rows = (
        Transaction.objects.filter(owner=user, kind=Kind.EXPENSE, date__gte=start, date__lt=end)
        .values("category__name", "category__color")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    grand = sum((r["total"] for r in rows), Decimal("0"))
    result, cursor = [], Decimal("0")
    for r in rows:
        percent = (r["total"] / grand * 100) if grand else Decimal("0")
        result.append(
            {
                "name": r["category__name"] or "Sin categoría",
                "color": r["category__color"] or "slate",
                "total": r["total"],
                "percent": round(percent, 1),
                "start": round(cursor, 2),
                "end": round(cursor + percent, 2),
            }
        )
        cursor += percent
    return result


def last_months_summary(user, year: int, month: int, count: int = 6):
    """Ingresos y gastos de los últimos `count` meses, para la gráfica de barras."""
    last_first = date(year, month, 1)
    first = add_months(last_first, -(count - 1))
    end = add_months(last_first, 1)
    buckets = OrderedDict()
    for i in range(count):
        d = add_months(first, i)
        buckets[(d.year, d.month)] = {
            "label": MONTHS_ES[d.month - 1],
            "key": f"{d.year}-{d.month:02d}",
            "income": Decimal("0"),
            "expense": Decimal("0"),
        }
    rows = (
        Transaction.objects.filter(owner=user, date__gte=first, date__lt=end)
        .exclude(kind=Kind.TRANSFER)
        .annotate(m=TruncMonth("date"))
        .values("m", "kind")
        .annotate(total=Sum("amount"))
    )
    for r in rows:
        bucket = buckets.get((r["m"].year, r["m"].month))
        if bucket:
            field = "income" if r["kind"] == Kind.INCOME else "expense"
            bucket[field] = r["total"]
    peak = max([b["income"] for b in buckets.values()] + [b["expense"] for b in buckets.values()])
    for b in buckets.values():
        b["income_pct"] = round(b["income"] / peak * 100, 1) if peak else 0
        b["expense_pct"] = round(b["expense"] / peak * 100, 1) if peak else 0
    return list(buckets.values())


def upcoming_payments(user, days: int = 30):
    today = timezone.localdate()
    return (
        Recurring.objects.filter(
            owner=user, is_active=True, next_date__lte=today + timedelta(days=days)
        )
        .exclude(kind=Kind.INCOME)
        .select_related("account", "category", "to_account")
        .order_by("next_date")
    )
