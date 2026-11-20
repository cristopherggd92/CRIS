from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.finance.templatetags.money import money

from . import services
from .forms import FORMS
from .models import Asset, Bill, Maintenance, Reminder, Service, Vehicle

DEFAULT_PAGE = {
    "servicio": "household:services",
    "recibo": "household:services",
    "vehiculo": "household:vehicles",
    "mantenimiento": "household:maintenance",
    "recordatorio": "household:agenda",
    "articulo": "household:inventory",
}


def _is_fetch(request):
    return request.headers.get("x-requested-with") == "fetch"


def _next(request, kind):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}):
        return target
    return reverse(DEFAULT_PAGE[kind])


def _done(request, message, kind):
    """Respuesta común de las acciones: JSON para JavaScript o redirect normal."""
    if _is_fetch(request):
        return JsonResponse({"ok": True, "message": message, "redirect": _next(request, kind)})
    messages.success(request, message)
    return redirect(_next(request, kind))


def finance_url(amount, concept, when, category):
    params = {
        "tipo": "gasto",
        "monto": amount or "",
        "concepto": concept[:120],
        "fecha": when.isoformat(),
        "categoria": category,
    }
    return f"{reverse('finance:transaction_create')}?{urlencode(params)}"


# ---------- Páginas ----------


def home(request):
    user = request.user
    today = timezone.localdate()
    items = services.agenda(user)
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    to_pay = sum(
        (e["amount"] or Decimal("0"))
        for e in items
        if e["kind"] in ("recibo", "servicio") and e["date"] < month_end
    )
    year_maint = Maintenance.objects.filter(owner=user, date__year=today.year).aggregate(
        total=Sum("cost")
    )["total"] or Decimal("0")
    costs = services.monthly_costs(user)
    context = {
        "groups": services.group_agenda(items),
        "overdue": sum(1 for e in items if e["state"] == "overdue"),
        "to_pay": to_pay,
        "year_maint": year_maint,
        "warranties": sum(
            1
            for a in Asset.objects.filter(owner=user, warranty_months__gt=0)
            if a.warranty_state in ("active", "expiring")
        ),
        "costs": costs,
        "costs_total": sum(c["total"] for c in costs),
        "counts": {
            "servicios": Service.objects.filter(owner=user, is_active=True).count(),
            "vehiculos": Vehicle.objects.filter(owner=user).count(),
            "articulos": Asset.objects.filter(owner=user).count(),
        },
    }
    return render(request, "household/home.html", context)


def services_page(request):
    user = request.user
    svc = list(
        Service.objects.filter(owner=user).annotate(
            unpaid=Count("bills", filter=Q(bills__paid_at__isnull=True))
        )
    )
    bills = Bill.objects.filter(owner=user).select_related("service")[:60]
    year = timezone.localdate().year
    paid_year = Bill.objects.filter(owner=user, paid_at__year=year).aggregate(t=Sum("amount"))["t"]
    return render(
        request,
        "household/services.html",
        {
            "services": svc,
            "bills": bills,
            "paid_year": paid_year or Decimal("0"),
            "monthly": sum(
                (s.usual_amount or 0)
                / {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}[
                    s.frequency
                ]
                for s in svc
                if s.is_active
            ),
        },
    )


def vehicles_page(request):
    user = request.user
    vehicles = list(Vehicle.objects.filter(owner=user))
    year = timezone.localdate().year
    for v in vehicles:
        v.upcoming = list(v.reminders.filter(done_at__isnull=True).order_by("due_date")[:4])
        v.last_services = list(v.maintenances.all()[:3])
        v.year_cost = v.maintenances.filter(date__year=year).aggregate(t=Sum("cost"))["t"] or 0
        v.pending = [m for m in services.pending_maintenance(user) if m.vehicle_id == v.pk]
    return render(request, "household/vehicles.html", {"vehicles": vehicles})


def maintenance_page(request):
    records = Maintenance.objects.filter(owner=request.user).select_related("vehicle")
    return render(
        request,
        "household/maintenance.html",
        {
            "records": records,
            "total": records.aggregate(t=Sum("cost"))["t"] or Decimal("0"),
            "areas": Maintenance.Area.choices,
        },
    )


def agenda_page(request):
    reminders = Reminder.objects.filter(owner=request.user).select_related("vehicle")
    return render(
        request,
        "household/agenda.html",
        {
            "pending": reminders.filter(done_at__isnull=True).order_by("due_date"),
            "done": reminders.filter(done_at__isnull=False).order_by("-done_at")[:15],
        },
    )


def inventory_page(request):
    assets = list(Asset.objects.filter(owner=request.user))
    return render(
        request,
        "household/inventory.html",
        {
            "assets": assets,
            "categories": Asset.Category.choices,
            "total_value": sum((a.price or 0) for a in assets),
            "with_warranty": sum(1 for a in assets if a.warranty_state in ("active", "expiring")),
        },
    )


# ---------- Formulario dinámico (panel lateral) ----------


def _initial(request, kind):
    g, user, initial = request.GET, request.user, {}
    if kind == "recibo" and g.get("servicio", "").isdigit():
        s = Service.objects.filter(owner=user, pk=g["servicio"]).first()
        if s:
            initial.update(service=s, amount=s.usual_amount, due_date=s.next_due)
    if kind in ("mantenimiento", "recordatorio") and g.get("vehiculo", "").isdigit():
        v = Vehicle.objects.filter(owner=user, pk=g["vehiculo"]).first()
        if v:
            initial.update(vehicle=v, area=Maintenance.Area.CAR, km=v.km or None)
    if kind == "mantenimiento" and g.get("repetir", "").isdigit():
        # "Registrar" desde la agenda: copia el servicio anterior
        m = Maintenance.objects.filter(owner=user, pk=g["repetir"]).first()
        if m:
            initial.update(
                area=m.area,
                vehicle=m.vehicle,
                title=m.title,
                provider=m.provider,
                km=m.vehicle.km if m.vehicle else None,
            )
    if kind == "mantenimiento" and g.get("area") in Maintenance.Area.values:
        initial["area"] = g["area"]
    return initial


def _form_context(request, kind, form, obj):
    user = request.user
    ctx = {
        "form": form,
        "kind": kind,
        "object": obj,
        "next": _next(request, kind),
        "label": FORMS[kind][2],
    }
    if kind == "recibo":
        ctx["services_json"] = {
            s.pk: {"amount": str(s.usual_amount or ""), "due": s.next_due.isoformat()}
            for s in Service.objects.filter(owner=user)
        }
    if kind == "mantenimiento":
        ctx["vehicles_json"] = {v.pk: v.km for v in Vehicle.objects.filter(owner=user)}
    if kind == "articulo":
        ctx["locations"] = (
            Asset.objects.filter(owner=user)
            .exclude(location="")
            .values_list("location", flat=True)
            .distinct()
        )
    return ctx


def form_view(request, kind, pk=None):
    if kind not in FORMS:
        raise Http404
    model, form_class, label = FORMS[kind]
    obj = get_object_or_404(model, pk=pk, owner=request.user) if pk else None
    form = form_class(
        request.POST or None,
        instance=obj,
        owner=request.user,
        initial=None if obj else _initial(request, kind),
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            msg = f"{label.capitalize()} {'actualizado' if obj else 'guardado'}."
            return _done(request, msg, kind)
        status = 400
    else:
        status = 200
    ctx = _form_context(request, kind, form, obj)
    template = f"household/forms/{kind}.html"
    if _is_fetch(request):
        return render(request, template, ctx, status=status)
    ctx["form_template"] = template
    return render(request, "household/form_page.html", ctx, status=status)


@require_POST
def delete_view(request, kind, pk):
    if kind not in FORMS:
        raise Http404
    model, _, label = FORMS[kind]
    get_object_or_404(model, pk=pk, owner=request.user).delete()
    return _done(request, f"{label.capitalize()} eliminado.", kind)


# ---------- Acciones rápidas ----------


@require_POST
def bill_pay(request, pk):
    bill = get_object_or_404(Bill, pk=pk, owner=request.user)
    if not bill.is_paid:
        bill.pay()
    data = {
        "ok": True,
        "message": f"Recibo de {bill.service.name} pagado.",
        "finance_url": finance_url(
            bill.amount, f"{bill.service.name} {bill.period}".strip(), bill.paid_at, "Servicios"
        ),
    }
    if _is_fetch(request):
        return JsonResponse(data)
    messages.success(request, data["message"])
    return redirect(_next(request, "recibo"))


@require_POST
def service_pay(request, pk):
    """Pagar en un clic: crea el recibo con el monto habitual (o el que escribas) y lo paga."""
    service = get_object_or_404(Service, pk=pk, owner=request.user)
    raw = request.POST.get("amount", "").strip().replace(",", ".")
    try:
        amount = Decimal(raw) if raw else service.usual_amount
    except InvalidOperation:
        amount = None
    if amount is None or amount < 0:
        msg = "Escribe el monto del recibo."
        if _is_fetch(request):
            return JsonResponse({"ok": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect(_next(request, "servicio"))
    bill = Bill.objects.create(
        owner=request.user, service=service, amount=amount, due_date=service.next_due
    )
    bill.pay()
    data = {
        "ok": True,
        "message": f"{service.name}: pagado {money(amount)}. Próximo: {service.next_due:%d/%m/%Y}.",
        "finance_url": finance_url(amount, service.name, bill.paid_at, "Servicios"),
    }
    if _is_fetch(request):
        return JsonResponse(data)
    messages.success(request, data["message"])
    return redirect(_next(request, "servicio"))


@require_POST
def reminder_done(request, pk):
    reminder = get_object_or_404(Reminder, pk=pk, owner=request.user, done_at__isnull=True)
    finished = reminder.complete()
    msg = (
        f"«{reminder.title}» completado."
        if finished
        else f"«{reminder.title}» listo. Siguiente: {reminder.due_date:%d/%m/%Y}."
    )
    data = {"ok": True, "message": msg}
    if reminder.amount:
        data["finance_url"] = finance_url(
            reminder.amount, reminder.title, timezone.localdate(), "Transporte"
        )
    if _is_fetch(request):
        return JsonResponse(data)
    messages.success(request, msg)
    return redirect(_next(request, "recordatorio"))


@require_POST
def vehicle_km(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk, owner=request.user)
    try:
        km = int(request.POST.get("km", ""))
    except ValueError:
        return JsonResponse({"ok": False, "message": "Kilometraje inválido."}, status=400)
    if km < 0 or km > 3_000_000:
        return JsonResponse({"ok": False, "message": "Kilometraje inválido."}, status=400)
    vehicle.km = km
    vehicle.save(update_fields=["km"])
    return JsonResponse({"ok": True, "message": f"Kilometraje actualizado: {km:,} km."})
