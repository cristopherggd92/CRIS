"""Importador de movimientos desde un CSV exportado de NEKO.

Formato esperado (encabezados):
    Posted Date, Transaction Type, Description, Amount, Account,
    Category Group, Category, Notes

Reglas:
* El signo del monto decide si es gasto (−) o ingreso (+). "Pago" es un gasto.
* NEKO exporta cada transferencia en dos renglones (−origen y +destino); aquí
  se unen en una sola transferencia. Si falta su pareja, se importa como
  gasto o ingreso y se avisa.
* Cada renglón genera una huella (import_ref) para no duplicar si se vuelve
  a importar el mismo archivo.
"""

import csv
import hashlib
import io
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import TAG_COLORS_FOR_IMPORT, Account, Category, Kind, Recurring, Transaction
from .services import add_months

REQUIRED = {"Posted Date", "Transaction Type", "Description", "Amount", "Account"}
MAX_BYTES = 2 * 1024 * 1024


def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


@dataclass
class Row:
    line: int
    date: str
    kind: str
    amount: str  # siempre positivo, como texto (para guardarlo en sesión)
    account: str
    description: str
    category: str = ""
    to_account: str = ""
    is_payment: bool = False
    ref: str = ""
    warning: str = ""


@dataclass
class ParseResult:
    rows: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_session(self):
        return {"rows": [asdict(r) for r in self.rows], "errors": self.errors}

    @classmethod
    def from_session(cls, data):
        return cls(rows=[Row(**r) for r in data["rows"]], errors=data["errors"])


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer el archivo (codificación desconocida).")


def _amount(text):
    value = clean(text).replace("$", "").replace(",", "")
    return Decimal(value)


def parse_neko_csv(uploaded) -> ParseResult:
    raw = uploaded.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("El archivo pesa más de 2 MB.")
    reader = csv.DictReader(io.StringIO(_decode(raw)))
    headers = {clean(h) for h in (reader.fieldnames or [])}
    missing = REQUIRED - headers
    if missing:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(missing)))

    result = ParseResult()
    transfers = defaultdict(lambda: {"out": [], "in": []})
    seen = defaultdict(int)

    for line, raw_row in enumerate(reader, start=2):
        row = {clean(k): clean(v) for k, v in raw_row.items() if k}
        try:
            day = date.fromisoformat(row["Posted Date"])
            amount = _amount(row["Amount"])
        except (ValueError, InvalidOperation):
            result.errors.append(f"Renglón {line}: fecha o monto inválido, se omitió.")
            continue
        if amount == 0 or not row["Account"]:
            result.errors.append(f"Renglón {line}: sin monto o sin cuenta, se omitió.")
            continue

        ttype = row["Transaction Type"].lower()
        description = row["Description"]
        notes = row.get("Notes", "")
        if notes:
            description = f"{description} · {notes}" if description else notes
        item = Row(
            line=line,
            date=day.isoformat(),
            kind=Kind.EXPENSE if amount < 0 else Kind.INCOME,
            amount=str(abs(amount)),
            account=row["Account"],
            description=description[:120],
            category=row.get("Category", ""),
            is_payment=ttype == "pago",
        )
        # Huella: mismos datos + número de aparición dentro del archivo
        base = "|".join([item.date, ttype, description, row["Amount"], item.account])
        seen[base] += 1
        item.ref = hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest()

        if ttype.startswith("transfer"):
            key = (item.date, description.lower(), item.amount)
            transfers[key]["out" if amount < 0 else "in"].append(item)
        else:
            result.rows.append(item)

    # Une las dos mitades de cada transferencia
    for group in transfers.values():
        outs, ins = group["out"], group["in"]
        while outs and ins:
            src, dst = outs.pop(0), ins.pop(0)
            src.kind = Kind.TRANSFER
            src.to_account = dst.account
            src.category = ""
            src.ref = hashlib.sha1((src.ref + dst.ref).encode()).hexdigest()
            result.rows.append(src)
        for orphan in outs + ins:
            orphan.warning = "Transferencia sin pareja: se importará como gasto/ingreso."
            orphan.category = ""
            result.rows.append(orphan)

    result.rows.sort(key=lambda r: (r.date, r.line))
    return result


def _guess_account_type(name):
    n = name.lower()
    if "efectivo" in n or "cash" in n:
        return Account.Type.CASH
    if "tdc" in n or "crédito" in n or "credito" in n or "tarjeta" in n:
        return Account.Type.CREDIT
    if "ahorro" in n or "caja" in n or "fondo" in n:
        return Account.Type.SAVINGS
    if "inversi" in n:
        return Account.Type.INVESTMENT
    return Account.Type.DEBIT


def _color(name):
    return TAG_COLORS_FOR_IMPORT[sum(map(ord, name)) % len(TAG_COLORS_FOR_IMPORT)]


def analyze(user, result: ParseResult):
    """Resumen para la vista previa: qué es nuevo, qué es duplicado."""
    refs = [r.ref for r in result.rows]
    existing_refs = set(
        Transaction.objects.filter(owner=user, import_ref__in=refs).values_list(
            "import_ref", flat=True
        )
    )
    existing_accounts = {a.name.lower() for a in Account.objects.filter(owner=user)}
    existing_cats = {(c.kind, c.name.lower()) for c in Category.objects.filter(owner=user)}
    new_accounts, new_categories = set(), set()
    counts = defaultdict(int)
    for r in result.rows:
        r.duplicate = r.ref in existing_refs
        if r.duplicate:
            counts["duplicados"] += 1
            continue
        counts[r.kind] += 1
        for acc in filter(None, [r.account, r.to_account]):
            if acc.lower() not in existing_accounts:
                new_accounts.add(acc)
        if r.kind != Kind.TRANSFER and r.category:
            if (r.kind, r.category.lower()) not in existing_cats:
                new_categories.add(r.category)

    # Pagos únicos: candidatos a recurrentes (suscripciones, servicios…)
    payments = {}
    for r in result.rows:
        if r.is_payment and r.kind == Kind.EXPENSE:
            payments[r.description.lower()] = r
    return {
        "counts": {str(k): v for k, v in counts.items()},
        "to_import": sum(v for k, v in counts.items() if k != "duplicados"),
        "new_accounts": sorted(new_accounts),
        "new_categories": sorted(new_categories),
        "recurring_candidates": sorted(payments.values(), key=lambda r: r.description),
    }


@transaction.atomic
def import_rows(user, result: ParseResult, recurring_refs=()):
    accounts = {a.name.lower(): a for a in Account.objects.filter(owner=user)}
    categories = {(c.kind, c.name.lower()): c for c in Category.objects.filter(owner=user)}
    existing = set(
        Transaction.objects.filter(
            owner=user, import_ref__in=[r.ref for r in result.rows]
        ).values_list("import_ref", flat=True)
    )

    def account(name):
        key = name.lower()
        if key not in accounts:
            accounts[key] = Account.objects.create(
                owner=user, name=name[:60], type=_guess_account_type(name), color=_color(name)
            )
        return accounts[key]

    def category(kind, name):
        name = name or ("Otros gastos" if kind == Kind.EXPENSE else "Otros ingresos")
        key = (kind, name.lower())
        if key not in categories:
            categories[key] = Category.objects.create(
                owner=user, kind=kind, name=name[:40], color=_color(name)
            )
        return categories[key]

    created = skipped = 0
    batch = []
    for r in result.rows:
        if r.ref in existing:
            skipped += 1
            continue
        is_transfer = r.kind == Kind.TRANSFER
        batch.append(
            Transaction(
                owner=user,
                kind=r.kind,
                amount=Decimal(r.amount),
                date=date.fromisoformat(r.date),
                account=account(r.account),
                to_account=account(r.to_account) if is_transfer else None,
                category=None if is_transfer else category(r.kind, r.category),
                description=r.description,
                import_ref=r.ref,
            )
        )
        existing.add(r.ref)
        created += 1
    Transaction.objects.bulk_create(batch)

    # Recurrentes elegidas por el usuario: mensuales, a partir del próximo mes
    today = timezone.localdate()
    recurrings = 0
    chosen = set(recurring_refs)
    for r in result.rows:
        if r.ref not in chosen:
            continue
        next_date = add_months(date.fromisoformat(r.date), 1)
        while next_date <= today:
            next_date = add_months(next_date, 1)
        Recurring.objects.create(
            owner=user,
            kind=Kind.EXPENSE,
            description=r.description,
            amount=Decimal(r.amount),
            account=account(r.account),
            category=category(Kind.EXPENSE, r.category),
            frequency=Recurring.Frequency.MONTHLY,
            next_date=next_date,
        )
        recurrings += 1
    return {"created": created, "skipped": skipped, "recurrings": recurrings}
