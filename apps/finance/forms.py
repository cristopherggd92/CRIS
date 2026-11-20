from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import Account, Category, Kind, Recurring, Transaction


class OwnedFormMixin:
    """Limita cuentas y categorías a las del usuario y valida tipo/destino."""

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        # Cuentas activas + las que ya usa este registro (aunque estén archivadas)
        used = [i for i in (self.instance.account_id, self.instance.to_account_id) if i]
        accounts = Account.objects.filter(owner=owner).filter(Q(is_archived=False) | Q(pk__in=used))
        self.fields["account"].queryset = accounts
        self.fields["to_account"].queryset = accounts
        self.fields["category"].queryset = Category.objects.filter(owner=owner)
        # Gasto primero: es lo que más se registra
        order = [Kind.EXPENSE, Kind.INCOME, Kind.TRANSFER]
        choices = [(k.value, k.label) for k in order]
        self.fields["kind"].choices = choices
        self.fields["kind"].widget = forms.RadioSelect(choices=choices)

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        category = data.get("category")
        if kind == Kind.TRANSFER:
            if not data.get("to_account"):
                self.add_error("to_account", "Elige la cuenta destino.")
            elif data.get("to_account") == data.get("account"):
                self.add_error("to_account", "La cuenta destino debe ser distinta.")
            data["category"] = None
        else:
            data["to_account"] = None
            if category and category.kind != kind:
                self.add_error("category", "La categoría no corresponde al tipo.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.owner = self.owner
        if commit:
            obj.save()
        return obj


class TransactionForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["kind", "amount", "date", "account", "to_account", "category", "description"]
        widgets = {
            "amount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.TextInput(attrs={"placeholder": "Ej. Súper de la semana"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()


class RecurringForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = Recurring
        fields = [
            "kind",
            "description",
            "amount",
            "frequency",
            "next_date",
            "end_date",
            "account",
            "to_account",
            "category",
            "is_active",
        ]
        widgets = {
            "amount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "next_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.TextInput(attrs={"placeholder": "Ej. Renta, Netflix, Salario"}),
        }
        labels = {"next_date": "Próximo cobro / pago"}

    def clean(self):
        data = super().clean()
        if data.get("end_date") and data.get("next_date") and data["end_date"] < data["next_date"]:
            self.add_error("end_date", "Debe ser posterior a la próxima fecha.")
        return data


class AccountForm(forms.ModelForm):
    current_balance = forms.DecimalField(
        label="Saldo actual",
        required=False,
        max_digits=12,
        decimal_places=2,
        help_text="Opcional. Escribe el saldo que ves hoy en tu banco (o en NEKO) y CRIS "
        "calcula el saldo inicial para que cuadre.",
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "Ej. 12500.00"}),
    )

    class Meta:
        model = Account
        fields = ["name", "type", "initial_balance", "color", "is_archived"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej. BBVA Nómina"}),
            "initial_balance": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Account.objects.filter(owner=self.owner, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya tienes una cuenta con ese nombre.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.owner = self.owner
        target = self.cleaned_data.get("current_balance")
        if target is not None:
            # saldo = inicial + movimientos  =>  inicial = saldo deseado − movimientos
            movements = (obj.balance - obj.initial_balance) if obj.pk else 0
            obj.initial_balance = target - movements
        if commit:
            obj.save()
        return obj


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "color"]

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        name, kind = data.get("name", "").strip(), data.get("kind")
        qs = Category.objects.filter(owner=self.owner, kind=kind, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if name and qs.exists():
            self.add_error("name", "Ya existe una categoría con ese nombre.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.owner = self.owner
        if commit:
            obj.save()
        return obj


class ImportForm(forms.Form):
    file = forms.FileField(
        label="Archivo CSV",
        help_text="Exportado desde NEKO. Máximo 2 MB.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Debe ser un archivo .csv")
        return f
