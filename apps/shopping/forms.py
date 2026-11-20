from django import forms

from .models import Item, Product, ShoppingList

MONEY_ATTRS = {"step": "0.01", "min": "0", "placeholder": "0.00", "inputmode": "decimal"}


class ShoppingListForm(forms.ModelForm):
    class Meta:
        model = ShoppingList
        fields = ["name", "store", "planned_date", "budget", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej.: Despensa semanal"}),
            "store": forms.TextInput(
                attrs={"placeholder": "Walmart, Soriana, Costco…", "list": "stores"}
            ),
            "planned_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "budget": forms.NumberInput(attrs=MONEY_ATTRS),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Opcional"}),
        }


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["name", "quantity", "unit", "aisle", "price", "note"]
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "¿Qué necesitas?", "list": "products", "autocomplete": "off"}
            ),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "price": forms.NumberInput(attrs=MONEY_ATTRS),
            "note": forms.TextInput(attrs={"placeholder": "Marca, tamaño… (opcional)"}),
        }

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def save(self, commit=True):
        item = super().save(commit=False)
        product = Product.objects.filter(owner=self.owner, name__iexact=item.name).first()
        if product is None:
            product = Product.objects.create(
                owner=self.owner,
                name=item.name,
                aisle=item.aisle,
                unit=item.unit,
                last_price=item.price,
            )
        else:
            # Lo que capturas manda: el catálogo aprende el pasillo y la unidad
            product.aisle, product.unit = item.aisle, item.unit
            if product.last_price is None and item.price is not None:
                product.last_price = item.price
            product.save()
        item.product = product
        if commit:
            item.save()
        return item


class CompleteForm(forms.Form):
    total_paid = forms.DecimalField(
        label="Total pagado en caja",
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        help_text="Déjalo vacío para usar el total de lo que marcaste.",
        widget=forms.NumberInput(attrs=MONEY_ATTRS),
    )
    carry_over = forms.BooleanField(
        label="Pasar lo que no encontré a una lista nueva",
        required=False,
        initial=True,
    )


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "aisle", "unit", "last_price", "is_favorite"]
        widgets = {"last_price": forms.NumberInput(attrs=MONEY_ATTRS)}

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        clash = Product.objects.filter(owner=self.owner, name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("Ya tienes un producto con ese nombre.")
        return name
