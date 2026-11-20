from django import forms
from django.utils import timezone

from .models import Asset, Bill, Maintenance, Reminder, Service, Vehicle

DATE = {"type": "date"}
MONEY = {"step": "0.01", "min": "0", "placeholder": "0.00", "inputmode": "decimal"}
VEHICLE_COLORS = ["indigo", "emerald", "amber", "rose", "sky", "violet", "teal", "orange"]


def date_widget():
    return forms.DateInput(attrs=DATE, format="%Y-%m-%d")


class OwnerForm(forms.ModelForm):
    """Recibe al dueño, limita los catálogos relacionados y lo asigna al guardar."""

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        if "vehicle" in self.fields:
            self.fields["vehicle"].queryset = Vehicle.objects.filter(owner=owner)
            self.fields["vehicle"].empty_label = "Sin vehículo"
        if "service" in self.fields:
            self.fields["service"].queryset = Service.objects.filter(owner=owner)
            self.fields["service"].empty_label = "Elige un servicio"

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.owner = self.owner
        if commit:
            obj.save()
        return obj


class ServiceForm(OwnerForm):
    class Meta:
        model = Service
        fields = [
            "kind",
            "name",
            "provider",
            "account_number",
            "frequency",
            "next_due",
            "usual_amount",
            "is_active",
        ]
        widgets = {
            "kind": forms.RadioSelect,
            "frequency": forms.RadioSelect,
            "name": forms.TextInput(attrs={"placeholder": "Ej.: Luz de la casa"}),
            "provider": forms.TextInput(attrs={"list": "providers", "placeholder": "CFE, Izzi…"}),
            "next_due": date_widget(),
            "usual_amount": forms.NumberInput(attrs=MONEY),
        }


class BillForm(OwnerForm):
    paid = forms.BooleanField(label="Ya lo pagué", required=False)

    class Meta:
        model = Bill
        fields = ["service", "amount", "due_date", "period", "reference"]
        widgets = {
            "amount": forms.NumberInput(attrs=MONEY),
            "due_date": date_widget(),
            "period": forms.TextInput(attrs={"placeholder": "Ej.: Nov–Dic 2026"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["paid"].initial = self.instance.is_paid

    def save(self, commit=True):
        bill = super().save(commit=commit)
        if commit:
            if self.cleaned_data["paid"] and not bill.is_paid:
                bill.pay()
            elif not self.cleaned_data["paid"] and bill.is_paid:
                bill.paid_at = None
                bill.save(update_fields=["paid_at"])
        return bill


class VehicleForm(OwnerForm):
    # Atajos solo al dar de alta: crean recordatorios automáticamente
    verification_date = forms.DateField(
        label="Próxima verificación", required=False, widget=date_widget()
    )
    insurance_date = forms.DateField(
        label="Vencimiento del seguro", required=False, widget=date_widget()
    )
    tax_date = forms.DateField(label="Tenencia / refrendo", required=False, widget=date_widget())

    class Meta:
        model = Vehicle
        fields = ["name", "brand", "model", "year", "plate", "km", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej.: El Versa"}),
            "year": forms.NumberInput(attrs={"min": 1950, "max": 2100, "placeholder": "2020"}),
            "plate": forms.TextInput(attrs={"placeholder": "ABC-123-D", "class": "input-upper"}),
            "km": forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
            "color": forms.RadioSelect(choices=[(c, c) for c in VEHICLE_COLORS]),
        }

    def clean_plate(self):
        return self.cleaned_data["plate"].upper().strip()

    def save(self, commit=True):
        is_new = self.instance.pk is None
        vehicle = super().save(commit=commit)
        if commit and is_new:
            shortcuts = [
                ("verification_date", Reminder.Category.VERIFICATION, "Verificación", "semestral"),
                ("insurance_date", Reminder.Category.INSURANCE, "Seguro", "anual"),
                ("tax_date", Reminder.Category.TAX, "Tenencia / refrendo", "anual"),
            ]
            for field, category, label, repeat in shortcuts:
                when = self.cleaned_data.get(field)
                if when:
                    Reminder.objects.create(
                        owner=self.owner,
                        vehicle=vehicle,
                        category=category,
                        title=f"{label} · {vehicle.name}",
                        due_date=when,
                        repeat=repeat,
                    )
        return vehicle


class MaintenanceForm(OwnerForm):
    class Meta:
        model = Maintenance
        fields = [
            "area",
            "vehicle",
            "title",
            "date",
            "cost",
            "km",
            "provider",
            "next_date",
            "next_km",
            "notes",
        ]
        widgets = {
            "area": forms.RadioSelect,
            "title": forms.TextInput(attrs={"placeholder": "Ej.: Cambio de aceite"}),
            "date": date_widget(),
            "cost": forms.NumberInput(attrs=MONEY),
            "km": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
            "next_date": date_widget(),
            "next_km": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Refacciones, garantía…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()

    def clean(self):
        data = super().clean()
        if data.get("area") == Maintenance.Area.CAR:
            if not data.get("vehicle") and self.fields["vehicle"].queryset.exists():
                self.add_error("vehicle", "Elige el vehículo.")
        else:
            data["vehicle"] = None
            data["km"] = data["next_km"] = None
        km, next_km = data.get("km"), data.get("next_km")
        if km and next_km and next_km <= km:
            self.add_error("next_km", "Debe ser mayor al kilometraje del servicio.")
        if data.get("date") and data.get("next_date") and data["next_date"] <= data["date"]:
            self.add_error("next_date", "Debe ser posterior a la fecha del servicio.")
        return data

    def save(self, commit=True):
        record = super().save(commit=commit)
        vehicle = record.vehicle
        if commit and vehicle and record.km and record.km > vehicle.km:
            vehicle.km = record.km  # el odómetro avanza solo
            vehicle.save(update_fields=["km"])
        return record


class ReminderForm(OwnerForm):
    class Meta:
        model = Reminder
        fields = ["category", "title", "vehicle", "due_date", "repeat", "amount", "notes"]
        widgets = {
            "category": forms.RadioSelect,
            "repeat": forms.RadioSelect,
            "title": forms.TextInput(attrs={"placeholder": "Ej.: Verificación 2° semestre"}),
            "due_date": date_widget(),
            "amount": forms.NumberInput(attrs=MONEY),
            "notes": forms.TextInput(attrs={"placeholder": "Opcional"}),
        }


class AssetForm(OwnerForm):
    class Meta:
        model = Asset
        fields = [
            "category",
            "name",
            "brand",
            "serial",
            "location",
            "store",
            "purchase_date",
            "price",
            "warranty_months",
            "notes",
        ]
        widgets = {
            "category": forms.RadioSelect,
            "name": forms.TextInput(attrs={"placeholder": "Ej.: Refrigerador"}),
            "location": forms.TextInput(attrs={"list": "locations", "placeholder": "Cocina"}),
            "purchase_date": date_widget(),
            "price": forms.NumberInput(attrs=MONEY),
            "warranty_months": forms.NumberInput(attrs={"min": 0, "max": 240}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Dónde está la factura…"}),
        }


FORMS = {
    "servicio": (Service, ServiceForm, "servicio"),
    "recibo": (Bill, BillForm, "recibo"),
    "vehiculo": (Vehicle, VehicleForm, "vehículo"),
    "mantenimiento": (Maintenance, MaintenanceForm, "mantenimiento"),
    "recordatorio": (Reminder, ReminderForm, "recordatorio"),
    "articulo": (Asset, AssetForm, "artículo"),
}
