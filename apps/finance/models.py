from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum

MONEY = {"max_digits": 12, "decimal_places": 2}
POSITIVE = [MinValueValidator(Decimal("0.01"))]

COLORS = [
    ("slate", "Gris"),
    ("indigo", "Índigo"),
    ("emerald", "Verde"),
    ("amber", "Ámbar"),
    ("rose", "Rosa"),
    ("sky", "Azul"),
    ("violet", "Violeta"),
    ("teal", "Turquesa"),
    ("orange", "Naranja"),
]

TAG_COLORS_FOR_IMPORT = [c for c, _ in COLORS if c != "slate"]


class Kind(models.TextChoices):
    INCOME = "ingreso", "Ingreso"
    EXPENSE = "gasto", "Gasto"
    TRANSFER = "transferencia", "Transferencia"


class Account(models.Model):
    class Type(models.TextChoices):
        CASH = "efectivo", "Efectivo"
        DEBIT = "debito", "Débito"
        CREDIT = "credito", "Tarjeta de crédito"
        SAVINGS = "ahorro", "Ahorro"
        INVESTMENT = "inversion", "Inversión"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts"
    )
    name = models.CharField("nombre", max_length=60)
    type = models.CharField("tipo", max_length=20, choices=Type.choices, default=Type.DEBIT)
    initial_balance = models.DecimalField(
        "saldo inicial",
        default=0,
        help_text="Para tarjetas de crédito, captura la deuda actual en negativo.",
        **MONEY,
    )
    color = models.CharField(max_length=20, choices=COLORS, default="slate")
    is_archived = models.BooleanField("archivada", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_archived", "name"]
        verbose_name = "cuenta"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_account_per_owner"),
        ]

    def __str__(self):
        return self.name

    @property
    def icon(self):
        return {
            self.Type.CASH: "cash",
            self.Type.DEBIT: "bank",
            self.Type.CREDIT: "card",
            self.Type.SAVINGS: "piggy",
            self.Type.INVESTMENT: "chart",
        }.get(self.type, "wallet")

    @property
    def balance(self):
        """Saldo = inicial + ingresos − gastos − transferencias enviadas + recibidas."""
        sums = Transaction.objects.aggregate(
            income=Sum("amount", filter=Q(account=self, kind=Kind.INCOME)),
            expense=Sum("amount", filter=Q(account=self, kind=Kind.EXPENSE)),
            sent=Sum("amount", filter=Q(account=self, kind=Kind.TRANSFER)),
            received=Sum("amount", filter=Q(to_account=self, kind=Kind.TRANSFER)),
        )
        zero = Decimal("0")
        return (
            self.initial_balance
            + (sums["income"] or zero)
            - (sums["expense"] or zero)
            - (sums["sent"] or zero)
            + (sums["received"] or zero)
        )


class Category(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField("nombre", max_length=40)
    kind = models.CharField(
        "tipo",
        max_length=20,
        choices=[(Kind.INCOME, "Ingreso"), (Kind.EXPENSE, "Gasto")],
        default=Kind.EXPENSE,
    )
    color = models.CharField(max_length=20, choices=COLORS, default="slate")

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = "categoría"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "kind", "name"], name="unique_category_per_owner"
            ),
        ]

    def __str__(self):
        return self.name


DEFAULT_CATEGORIES = {
    Kind.EXPENSE: [
        ("Comida", "orange"),
        ("Transporte", "sky"),
        ("Hogar", "teal"),
        ("Servicios", "indigo"),
        ("Salud", "rose"),
        ("Entretenimiento", "violet"),
        ("Compras", "amber"),
        ("Educación", "emerald"),
        ("Otros gastos", "slate"),
    ],
    Kind.INCOME: [
        ("Salario", "emerald"),
        ("Freelance", "sky"),
        ("Inversiones", "violet"),
        ("Otros ingresos", "slate"),
    ],
}


def ensure_default_categories(user):
    """Crea las categorías base la primera vez que el usuario entra al módulo."""
    if Category.objects.filter(owner=user).exists():
        return
    Category.objects.bulk_create(
        Category(owner=user, kind=kind, name=name, color=color)
        for kind, items in DEFAULT_CATEGORIES.items()
        for name, color in items
    )


class Recurring(models.Model):
    class Frequency(models.TextChoices):
        WEEKLY = "semanal", "Semanal"
        BIWEEKLY = "quincenal", "Quincenal"
        MONTHLY = "mensual", "Mensual"
        YEARLY = "anual", "Anual"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recurrings"
    )
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.EXPENSE)
    description = models.CharField("descripción", max_length=120)
    amount = models.DecimalField("monto", validators=POSITIVE, **MONEY)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="+", verbose_name="cuenta"
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="cuenta destino",
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="categoría"
    )
    frequency = models.CharField(
        "frecuencia", max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    next_date = models.DateField("próxima fecha")
    end_date = models.DateField("termina el", null=True, blank=True)
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ["-is_active", "next_date"]
        verbose_name = "recurrente"

    def __str__(self):
        return self.description


class Transaction(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.EXPENSE)
    amount = models.DecimalField("monto", validators=POSITIVE, **MONEY)
    date = models.DateField("fecha")
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transactions", verbose_name="cuenta"
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_transfers",
        verbose_name="cuenta destino",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="categoría",
    )
    description = models.CharField("descripción", max_length=120, blank=True)
    recurring = models.ForeignKey(
        Recurring, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    # Huella del renglón importado (CSV). Evita duplicar si importas el mismo archivo
    import_ref = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "movimiento"
        indexes = [models.Index(fields=["owner", "date"])]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} {self.date}"

    @property
    def signed_amount(self):
        if self.kind == Kind.EXPENSE:
            return -self.amount
        return self.amount


class FinanceLock(models.Model):
    """Contraseña fija (no dinámica) para entrar al módulo de Finanzas.

    Se guarda cifrada con el mismo algoritmo que las contraseñas de Django;
    nunca en texto plano.
    """

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="finance_lock"
    )
    password_hash = models.CharField(max_length=128)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "candado de finanzas"

    def __str__(self):
        return f"Candado de {self.owner}"
