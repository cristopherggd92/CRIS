"""Administración del hogar: servicios, recibos, vehículos, mantenimientos,
recordatorios (verificaciones, seguros…) e inventario con garantías."""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.finance.services import add_months

MONEY = {"max_digits": 12, "decimal_places": 2}
POSITIVE = [MinValueValidator(Decimal("0"))]
SOON_DAYS = 7


def due_state(due, today=None):
    """overdue / today / soon / ok según qué tan cerca está la fecha."""
    if not due:
        return ""
    today = today or timezone.localdate()
    if due < today:
        return "overdue"
    if due == today:
        return "today"
    if due <= today + timedelta(days=SOON_DAYS):
        return "soon"
    return "ok"


class Frequency(models.TextChoices):
    MONTHLY = "mensual", "Mensual"
    BIMONTHLY = "bimestral", "Bimestral"
    QUARTERLY = "trimestral", "Trimestral"
    SEMIANNUAL = "semestral", "Semestral"
    YEARLY = "anual", "Anual"


FREQ_MONTHS = {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}


def next_period(d: date, frequency: str) -> date:
    return add_months(d, FREQ_MONTHS.get(frequency, 1))


class Owned(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True


# ---------- Servicios y recibos ----------


class Service(Owned):
    class Kind(models.TextChoices):
        POWER = "luz", "Luz"
        WATER = "agua", "Agua"
        GAS = "gas", "Gas"
        INTERNET = "internet", "Internet / TV"
        PHONE = "telefono", "Telefonía"
        RENT = "renta", "Renta / Hipoteca"
        TAX = "predial", "Predial"
        FEES = "mantenimiento", "Cuota de mantenimiento"
        STREAMING = "streaming", "Suscripción"
        OTHER = "otro", "Otro"

    KIND_ICONS = {
        "luz": "bolt",
        "agua": "droplet",
        "gas": "flame",
        "internet": "wifi",
        "telefono": "phone",
        "renta": "home",
        "predial": "receipt",
        "mantenimiento": "wrench",
        "streaming": "play",
        "otro": "receipt",
    }

    name = models.CharField("nombre", max_length=60)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.POWER)
    provider = models.CharField("proveedor", max_length=60, blank=True)
    account_number = models.CharField("número de cuenta / contrato", max_length=40, blank=True)
    frequency = models.CharField(
        "periodicidad", max_length=12, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    next_due = models.DateField("próximo vencimiento")
    usual_amount = models.DecimalField(
        "monto habitual", null=True, blank=True, validators=POSITIVE, **MONEY
    )
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["next_due", "name"]
        verbose_name = "servicio"

    def __str__(self):
        return self.name

    @property
    def icon(self):
        return self.KIND_ICONS.get(self.kind, "receipt")

    @property
    def due_state(self):
        return due_state(self.next_due)


class Bill(Owned):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="bills", verbose_name="servicio"
    )
    amount = models.DecimalField("monto", validators=POSITIVE, **MONEY)
    due_date = models.DateField("fecha límite")
    period = models.CharField("periodo", max_length=40, blank=True)
    paid_at = models.DateField("pagado el", null=True, blank=True)
    reference = models.CharField("referencia / folio", max_length=60, blank=True)

    class Meta:
        ordering = ["-due_date"]
        verbose_name = "recibo"

    def __str__(self):
        return f"{self.service} {self.period or self.due_date}"

    @property
    def is_paid(self):
        return self.paid_at is not None

    @property
    def due_state(self):
        return "" if self.is_paid else due_state(self.due_date)

    def pay(self, when=None):
        """Marca pagado y, si era el recibo vigente, mueve el siguiente vencimiento."""
        self.paid_at = when or timezone.localdate()
        self.save(update_fields=["paid_at"])
        service = self.service
        if self.due_date >= service.next_due:
            service.next_due = next_period(self.due_date, service.frequency)
            service.save(update_fields=["next_due"])


# ---------- Vehículos y mantenimientos ----------


class Vehicle(Owned):
    name = models.CharField("alias", max_length=40)
    brand = models.CharField("marca", max_length=40, blank=True)
    model = models.CharField("modelo", max_length=40, blank=True)
    year = models.PositiveSmallIntegerField("año", null=True, blank=True)
    plate = models.CharField("placas", max_length=15, blank=True)
    km = models.PositiveIntegerField("kilometraje actual", default=0)
    color = models.CharField(max_length=20, default="indigo")

    class Meta:
        ordering = ["name"]
        verbose_name = "vehículo"

    def __str__(self):
        return self.name

    @property
    def description(self):
        return " ".join(str(x) for x in (self.brand, self.model, self.year) if x)


class Maintenance(Owned):
    """Un mantenimiento del auto o de la casa (con su costo)."""

    class Area(models.TextChoices):
        CAR = "auto", "Automóvil"
        PLUMBING = "plomeria", "Plomería"
        ELECTRIC = "electricidad", "Electricidad"
        APPLIANCE = "electrodomestico", "Electrodomésticos"
        GARDEN = "jardin", "Jardín"
        PAINT = "pintura", "Pintura / Albañilería"
        CLEANING = "limpieza", "Limpieza / Fumigación"
        OTHER = "otro", "Otro"

    title = models.CharField("trabajo realizado", max_length=80)
    area = models.CharField("área", max_length=20, choices=Area.choices, default=Area.CAR)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="maintenances",
        verbose_name="vehículo",
    )
    date = models.DateField("fecha")
    cost = models.DecimalField("costo", default=0, validators=POSITIVE, **MONEY)
    km = models.PositiveIntegerField("kilometraje", null=True, blank=True)
    provider = models.CharField("taller / proveedor", max_length=60, blank=True)
    next_date = models.DateField("próximo servicio (fecha)", null=True, blank=True)
    next_km = models.PositiveIntegerField("próximo servicio (km)", null=True, blank=True)
    notes = models.TextField("notas", blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "mantenimiento"

    def __str__(self):
        return self.title

    @property
    def is_car(self):
        return self.vehicle_id is not None or self.area == self.Area.CAR

    @property
    def km_left(self):
        if self.next_km and self.vehicle:
            return self.next_km - self.vehicle.km
        return None


# ---------- Recordatorios (verificación, seguro, tenencia…) ----------


class Reminder(Owned):
    class Category(models.TextChoices):
        VERIFICATION = "verificacion", "Verificación"
        INSURANCE = "seguro", "Seguro"
        TAX = "tenencia", "Tenencia / Refrendo"
        LICENSE = "licencia", "Licencia"
        SERVICE = "servicio", "Servicio programado"
        DOCUMENT = "documento", "Documento / Trámite"
        OTHER = "otro", "Otro"

    class Repeat(models.TextChoices):
        NONE = "", "No se repite"
        SEMIANNUAL = "semestral", "Cada 6 meses"
        YEARLY = "anual", "Cada año"
        BIENNIAL = "bienal", "Cada 2 años"

    CATEGORY_ICONS = {
        "verificacion": "check",
        "seguro": "shield",
        "tenencia": "receipt",
        "licencia": "card",
        "servicio": "wrench",
        "documento": "note",
        "otro": "bell",
    }
    REPEAT_MONTHS = {"semestral": 6, "anual": 12, "bienal": 24}

    title = models.CharField("recordatorio", max_length=80)
    category = models.CharField(
        "tipo", max_length=20, choices=Category.choices, default=Category.VERIFICATION
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reminders",
        verbose_name="vehículo",
    )
    due_date = models.DateField("fecha")
    repeat = models.CharField("repetir", max_length=12, choices=Repeat.choices, blank=True)
    amount = models.DecimalField(
        "costo estimado", null=True, blank=True, validators=POSITIVE, **MONEY
    )
    notes = models.CharField("notas", max_length=200, blank=True)
    done_at = models.DateField("completado el", null=True, blank=True)

    class Meta:
        ordering = ["due_date"]
        verbose_name = "recordatorio"

    def __str__(self):
        return self.title

    @property
    def icon(self):
        return self.CATEGORY_ICONS.get(self.category, "bell")

    @property
    def due_state(self):
        return "" if self.done_at else due_state(self.due_date)

    def complete(self):
        """Si se repite, avanza a la siguiente fecha; si no, queda completado."""
        months = self.REPEAT_MONTHS.get(self.repeat)
        if months:
            self.due_date = add_months(self.due_date, months)
            self.save(update_fields=["due_date"])
            return False
        self.done_at = timezone.localdate()
        self.save(update_fields=["done_at"])
        return True


# ---------- Inventario y garantías ----------


class Asset(Owned):
    class Category(models.TextChoices):
        ELECTRONICS = "electronica", "Electrónica"
        APPLIANCE = "electrodomestico", "Electrodoméstico"
        FURNITURE = "mueble", "Mueble"
        TOOL = "herramienta", "Herramienta"
        JEWELRY = "valor", "Joyería / Valor"
        DOCUMENT = "documento", "Documento importante"
        OTHER = "otro", "Otro"

    CATEGORY_ICONS = {
        "electronica": "phone",
        "electrodomestico": "bolt",
        "mueble": "home",
        "herramienta": "wrench",
        "valor": "star",
        "documento": "note",
        "otro": "box",
    }

    name = models.CharField("artículo", max_length=80)
    category = models.CharField(
        "categoría", max_length=20, choices=Category.choices, default=Category.ELECTRONICS
    )
    brand = models.CharField("marca / modelo", max_length=80, blank=True)
    serial = models.CharField("número de serie", max_length=60, blank=True)
    location = models.CharField("ubicación", max_length=60, blank=True)
    store = models.CharField("tienda", max_length=60, blank=True)
    purchase_date = models.DateField("fecha de compra", null=True, blank=True)
    price = models.DecimalField("precio", null=True, blank=True, validators=POSITIVE, **MONEY)
    warranty_months = models.PositiveSmallIntegerField("garantía (meses)", default=0)
    notes = models.TextField("notas", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "artículo de inventario"
        verbose_name_plural = "inventario"

    def __str__(self):
        return self.name

    @property
    def icon(self):
        return self.CATEGORY_ICONS.get(self.category, "box")

    @property
    def warranty_until(self):
        if self.purchase_date and self.warranty_months:
            return add_months(self.purchase_date, self.warranty_months)
        return None

    @property
    def warranty_state(self):
        """'' (sin garantía), active, expiring (≤30 días) o expired."""
        until = self.warranty_until
        if not until:
            return ""
        today = timezone.localdate()
        if until < today:
            return "expired"
        if until <= today + timedelta(days=30):
            return "expiring"
        return "active"
