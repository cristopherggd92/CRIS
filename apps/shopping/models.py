from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

MONEY = {"max_digits": 12, "decimal_places": 2}
POSITIVE = [MinValueValidator(Decimal("0"))]


class Aisle(models.TextChoices):
    """Pasillos en el orden típico de recorrido del súper."""

    PRODUCE = "frutas", "Frutas y verduras"
    BAKERY = "panaderia", "Panadería y tortillas"
    MEAT = "carnes", "Carnes y pescados"
    DAIRY = "lacteos", "Lácteos y huevo"
    PANTRY = "abarrotes", "Abarrotes y despensa"
    SNACKS = "botanas", "Botanas y dulces"
    DRINKS = "bebidas", "Bebidas"
    FROZEN = "congelados", "Congelados"
    CLEANING = "limpieza", "Limpieza del hogar"
    HYGIENE = "higiene", "Higiene personal"
    PETS = "bebe_mascotas", "Bebé y mascotas"
    OTHER = "otros", "Otros"


AISLE_ORDER = {value: i for i, value in enumerate(Aisle.values)}

AISLE_COLORS = {
    "frutas": "emerald",
    "panaderia": "amber",
    "carnes": "rose",
    "lacteos": "sky",
    "abarrotes": "orange",
    "botanas": "violet",
    "bebidas": "indigo",
    "congelados": "sky",
    "limpieza": "teal",
    "higiene": "violet",
    "bebe_mascotas": "amber",
    "otros": "indigo",
}


class Unit(models.TextChoices):
    PIECE = "pza", "pza"
    KG = "kg", "kg"
    GRAM = "g", "g"
    LITER = "l", "L"
    ML = "ml", "ml"
    PACK = "paq", "paquete"


class Product(models.Model):
    """Catálogo personal: se llena solo con lo que vas agregando a tus listas."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField("nombre", max_length=80)
    aisle = models.CharField("pasillo", max_length=20, choices=Aisle.choices, default=Aisle.OTHER)
    unit = models.CharField("unidad", max_length=5, choices=Unit.choices, default=Unit.PIECE)
    last_price = models.DecimalField(
        "último precio", null=True, blank=True, validators=POSITIVE, **MONEY
    )
    prev_price = models.DecimalField(
        "precio anterior", null=True, blank=True, validators=POSITIVE, **MONEY
    )
    last_store = models.CharField("última tienda", max_length=60, blank=True)
    last_bought_at = models.DateField("última compra", null=True, blank=True)
    times_bought = models.PositiveIntegerField("veces comprado", default=0)
    is_favorite = models.BooleanField("favorito", default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_product_per_owner"),
        ]
        verbose_name = "producto"

    def __str__(self):
        return self.name

    @property
    def aisle_color(self):
        return AISLE_COLORS.get(self.aisle, "indigo")

    @property
    def price_trend(self):
        """'up', 'down' o '' comparando el último precio contra el anterior."""
        if self.last_price is None or self.prev_price is None:
            return ""
        if self.last_price > self.prev_price:
            return "up"
        if self.last_price < self.prev_price:
            return "down"
        return ""

    @property
    def price_change_pct(self):
        if not self.price_trend or not self.prev_price:
            return None
        return round((self.last_price - self.prev_price) / self.prev_price * 100, 1)


class ShoppingList(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "activa", "Activa"
        DONE = "completada", "Completada"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_lists"
    )
    name = models.CharField("nombre de la lista", max_length=80)
    store = models.CharField("tienda", max_length=60, blank=True)
    planned_date = models.DateField("fecha de compra", null=True, blank=True)
    budget = models.DecimalField("presupuesto", null=True, blank=True, validators=POSITIVE, **MONEY)
    notes = models.TextField("notas", blank=True)
    status = models.CharField(
        "estatus", max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    total_paid = models.DecimalField(
        "total pagado", null=True, blank=True, validators=POSITIVE, **MONEY
    )
    created_at = models.DateTimeField("fecha de registro", auto_now_add=True)
    completed_at = models.DateTimeField("fecha de compra real", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "lista de compras"
        verbose_name_plural = "listas de compras"

    def __str__(self):
        return self.name

    @property
    def is_done(self):
        return self.status == self.Status.DONE

    def totals(self):
        """Resumen calculado en Python (las listas son chicas)."""
        items = list(self.items.all())
        estimated = sum((i.subtotal or Decimal("0")) for i in items)
        in_cart = sum((i.subtotal or Decimal("0")) for i in items if i.is_checked)
        checked = sum(1 for i in items if i.is_checked)
        count = len(items)
        return {
            "count": count,
            "checked": checked,
            "pending": count - checked,
            "progress": round(checked * 100 / count) if count else 0,
            "estimated": estimated,
            "in_cart": in_cart,
            "without_price": sum(1 for i in items if i.price is None),
            "budget_left": (self.budget - estimated) if self.budget is not None else None,
            "over_budget": self.budget is not None and estimated > self.budget,
        }

    def complete(self, total_paid=None):
        """Cierra la lista y actualiza el catálogo con los precios pagados."""
        today = timezone.localdate()
        for item in self.items.filter(is_checked=True).select_related("product"):
            product = item.product
            if not product:
                continue
            if item.price is not None:
                if product.last_price is not None and product.last_price != item.price:
                    product.prev_price = product.last_price
                product.last_price = item.price
            product.times_bought += 1
            product.last_bought_at = today
            if self.store:
                product.last_store = self.store
            product.save()
        self.status = self.Status.DONE
        self.completed_at = timezone.now()
        self.total_paid = total_paid if total_paid is not None else self.totals()["in_cart"]
        self.save()


class Item(models.Model):
    shopping_list = models.ForeignKey(
        ShoppingList, on_delete=models.CASCADE, related_name="items", verbose_name="lista"
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    name = models.CharField("artículo", max_length=80)
    quantity = models.DecimalField(
        "cantidad",
        max_digits=8,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField("unidad", max_length=5, choices=Unit.choices, default=Unit.PIECE)
    aisle = models.CharField("pasillo", max_length=20, choices=Aisle.choices, default=Aisle.OTHER)
    price = models.DecimalField(
        "precio unitario", null=True, blank=True, validators=POSITIVE, **MONEY
    )
    note = models.CharField("nota", max_length=120, blank=True)
    is_checked = models.BooleanField("en el carrito", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_checked", "name"]
        verbose_name = "artículo"

    def __str__(self):
        return self.name

    @property
    def subtotal(self):
        if self.price is None:
            return None
        return (self.quantity * self.price).quantize(Decimal("0.01"))

    @property
    def aisle_color(self):
        return AISLE_COLORS.get(self.aisle, "indigo")
