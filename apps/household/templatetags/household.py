from django import template

from ..models import Asset, Reminder, Service

register = template.Library()

AREA_ICONS = {
    "auto": "car",
    "plomeria": "droplet",
    "electricidad": "bolt",
    "electrodomestico": "box",
    "jardin": "flame",
    "pintura": "edit",
    "limpieza": "check",
    "otro": "wrench",
}
ICONS = {
    "service": Service.KIND_ICONS,
    "reminder": Reminder.CATEGORY_ICONS,
    "asset": Asset.CATEGORY_ICONS,
    "area": AREA_ICONS,
}
STATE_LABELS = {
    "overdue": "Vencido",
    "today": "Hoy",
    "soon": "Pronto",
    "ok": "Al corriente",
    "active": "Con garantía",
    "expiring": "Por vencer",
    "expired": "Vencida",
}


@register.filter
def choice_icon(value, group):
    return ICONS.get(group, {}).get(value, "bell")


@register.filter
def state_label(state):
    return STATE_LABELS.get(state, "")


@register.filter
def days_until(value):
    """'en 3 días', 'hoy', 'hace 2 días'."""
    from django.utils import timezone

    if not value:
        return ""
    delta = (value - timezone.localdate()).days
    if delta == 0:
        return "hoy"
    if delta == 1:
        return "mañana"
    if delta == -1:
        return "ayer"
    if delta > 0:
        return f"en {delta} días"
    return f"hace {-delta} días"


@register.filter
def km(value):
    try:
        return f"{int(value):,} km"
    except (TypeError, ValueError):
        return ""
