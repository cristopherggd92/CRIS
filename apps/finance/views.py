from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from . import importers, services
from .forms import AccountForm, CategoryForm, ImportForm, RecurringForm, TransactionForm
from .models import Account, Category, Kind, Recurring, Transaction, ensure_default_categories
from .security import finance_unlock_required, guard


class FinanceMixin:
    """Exige el candado de Finanzas, prepara al usuario y filtra por dueño."""

    model = None

    def dispatch(self, request, *args, **kwargs):
        blocked = guard(request)  # candado de Finanzas
        if blocked:
            return blocked
        if request.user.is_authenticated:
            ensure_default_categories(request.user)
            created = services.generate_due_recurring(request.user)
            if created and request.method == "GET":
                messages.info(request, f"Se registraron {created} movimientos recurrentes.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class OwnerFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Para que el formulario filtre categorías según el tipo elegido (JS)
        ctx["category_kinds"] = {
            str(c.pk): c.kind for c in Category.objects.filter(owner=self.request.user)
        }
        return ctx


def month_nav(year, month):
    current = date(year, month, 1)
    prev, nxt = services.add_months(current, -1), services.add_months(current, 1)
    return {
        "month_label": f"{services.MONTHS_ES_LONG[month - 1].capitalize()} {year}",
        "month_key": f"{year}-{month:02d}",
        "prev_month": f"{prev.year}-{prev.month:02d}",
        "next_month": f"{nxt.year}-{nxt.month:02d}",
    }


# ---------- Resumen ----------


class FinanceHomeView(FinanceMixin, TemplateView):
    template_name = "finance/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        year, month = services.parse_month(self.request.GET.get("mes"))
        accounts = list(Account.objects.filter(owner=user, is_archived=False))
        for acc in accounts:
            acc.current = acc.balance
        total = sum((a.current for a in accounts), Decimal("0"))
        upcoming = list(services.upcoming_payments(user))
        committed = sum((r.amount for r in upcoming if r.kind == Kind.EXPENSE), Decimal("0"))
        categories = services.expenses_by_category(user, year, month)
        ctx.update(
            month_nav(year, month),
            accounts=accounts,
            total_balance=total,
            safe_to_spend=total - committed,
            committed=committed,
            totals=services.month_totals(user, year, month),
            categories=categories,
            donut=", ".join(f"var(--c-{c['color']}) {c['start']}% {c['end']}%" for c in categories),
            months=services.last_months_summary(user, year, month),
            recent=Transaction.objects.filter(owner=user).select_related(
                "account", "to_account", "category"
            )[:8],
            upcoming=upcoming,
        )
        return ctx


# ---------- Movimientos ----------


class TransactionListView(FinanceMixin, ListView):
    model = Transaction
    template_name = "finance/transaction_list.html"
    context_object_name = "transactions"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related("account", "to_account", "category")
        g = self.request.GET
        self.year, self.month = services.parse_month(g.get("mes"))
        start, end = services.month_bounds(self.year, self.month)
        qs = qs.filter(date__gte=start, date__lt=end)
        if g.get("tipo") in Kind.values:
            qs = qs.filter(kind=g["tipo"])
        if g.get("cuenta", "").isdigit():
            acc = int(g["cuenta"])
            qs = qs.filter(Q(account_id=acc) | Q(to_account_id=acc))
        if g.get("categoria", "").isdigit():
            qs = qs.filter(category_id=int(g["categoria"]))
        if g.get("q"):
            qs = qs.filter(description__icontains=g["q"].strip())
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        query = self.request.GET.copy()
        query.pop("page", None)
        ctx.update(
            month_nav(self.year, self.month),
            totals=services.month_totals(user, self.year, self.month),
            filters=self.request.GET,
            querystring=query.urlencode(),
            accounts=Account.objects.filter(owner=user),
            categories=Category.objects.filter(owner=user),
            kinds=Kind.choices,
        )
        return ctx


class TransactionCreateView(FinanceMixin, OwnerFormMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "finance/transaction_form.html"

    def get_initial(self):
        """Acepta valores precargados por URL (p. ej. desde una compra del súper)."""
        g = self.request.GET
        initial = super().get_initial()
        initial["kind"] = g["tipo"] if g.get("tipo") in Kind.values else Kind.EXPENSE
        try:
            if g.get("monto"):
                initial["amount"] = Decimal(g["monto"])
        except ArithmeticError:
            pass
        try:
            if g.get("fecha"):
                initial["date"] = date.fromisoformat(g["fecha"])
        except ValueError:
            pass
        if g.get("concepto"):
            initial["description"] = g["concepto"][:120]
        # "categoria" acepta varias opciones en orden de preferencia: "Supermercado,Comida"
        for name in filter(None, (n.strip() for n in g.get("categoria", "").split(","))):
            category = Category.objects.filter(
                owner=self.request.user, name__iexact=name, kind=initial["kind"]
            ).first()
            if category:
                initial["category"] = category
                break
        return initial

    def get_success_url(self):
        messages.success(self.request, "Movimiento registrado.")
        target = self.request.GET.get("next")
        if target and url_has_allowed_host_and_scheme(target, {self.request.get_host()}):
            return target
        return reverse("finance:transactions")


class TransactionUpdateView(FinanceMixin, OwnerFormMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "finance/transaction_form.html"

    def get_success_url(self):
        messages.success(self.request, "Movimiento actualizado.")
        return reverse("finance:transactions") + f"?mes={self.object.date:%Y-%m}"


class TransactionDeleteView(FinanceMixin, DeleteView):
    model = Transaction
    template_name = "finance/confirm_delete.html"
    success_url = reverse_lazy("finance:transactions")

    def form_valid(self, form):
        messages.success(self.request, "Movimiento eliminado.")
        return super().form_valid(form)


# ---------- Cuentas ----------


class AccountListView(FinanceMixin, ListView):
    model = Account
    template_name = "finance/account_list.html"
    context_object_name = "accounts"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for acc in ctx["accounts"]:
            acc.current = acc.balance
        ctx["total_balance"] = sum(
            (a.current for a in ctx["accounts"] if not a.is_archived), Decimal("0")
        )
        return ctx


class AccountCreateView(FinanceMixin, OwnerFormMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = "finance/simple_form.html"
    success_url = reverse_lazy("finance:accounts")
    extra_context = {"title": "Nueva cuenta", "icon": "wallet"}


class AccountUpdateView(FinanceMixin, OwnerFormMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = "finance/simple_form.html"
    success_url = reverse_lazy("finance:accounts")
    extra_context = {"title": "Editar cuenta", "icon": "wallet"}


class AccountDeleteView(FinanceMixin, DeleteView):
    model = Account
    template_name = "finance/confirm_delete.html"
    success_url = reverse_lazy("finance:accounts")

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            self.object.is_archived = True
            self.object.save(update_fields=["is_archived"])
            messages.info(
                self.request,
                "La cuenta tiene movimientos, así que se archivó en lugar de borrarse.",
            )
            return redirect(self.success_url)
        messages.success(self.request, "Cuenta eliminada.")
        return response


# ---------- Recurrentes ----------


class RecurringListView(FinanceMixin, ListView):
    model = Recurring
    template_name = "finance/recurring_list.html"
    context_object_name = "recurrings"

    def get_queryset(self):
        return super().get_queryset().select_related("account", "to_account", "category")


class RecurringCreateView(FinanceMixin, OwnerFormMixin, CreateView):
    model = Recurring
    form_class = RecurringForm
    template_name = "finance/transaction_form.html"
    success_url = reverse_lazy("finance:recurring")
    extra_context = {"is_recurring": True}

    def get_initial(self):
        return {"kind": self.request.GET.get("tipo", Kind.EXPENSE)}


class RecurringUpdateView(FinanceMixin, OwnerFormMixin, UpdateView):
    model = Recurring
    form_class = RecurringForm
    template_name = "finance/transaction_form.html"
    success_url = reverse_lazy("finance:recurring")
    extra_context = {"is_recurring": True}


class RecurringDeleteView(FinanceMixin, DeleteView):
    model = Recurring
    template_name = "finance/confirm_delete.html"
    success_url = reverse_lazy("finance:recurring")


@require_POST
@finance_unlock_required
def recurring_toggle(request, pk):
    rec = get_object_or_404(Recurring, pk=pk, owner=request.user)
    rec.is_active = not rec.is_active
    rec.save(update_fields=["is_active"])
    return redirect("finance:recurring")


# ---------- Categorías ----------


class CategoryListView(FinanceMixin, ListView):
    model = Category
    template_name = "finance/category_list.html"
    context_object_name = "categories"


class CategoryCreateView(FinanceMixin, OwnerFormMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "finance/simple_form.html"
    success_url = reverse_lazy("finance:categories")
    extra_context = {"title": "Nueva categoría", "icon": "tag"}


class CategoryUpdateView(FinanceMixin, OwnerFormMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "finance/simple_form.html"
    success_url = reverse_lazy("finance:categories")
    extra_context = {"title": "Editar categoría", "icon": "tag"}


class CategoryDeleteView(FinanceMixin, DeleteView):
    model = Category
    template_name = "finance/confirm_delete.html"
    success_url = reverse_lazy("finance:categories")


# ---------- Importar CSV ----------

SESSION_KEY = "finance_import"


class ImportView(FinanceMixin, TemplateView):
    """Paso 1: subir el archivo. Paso 2: vista previa. Paso 3: confirmar."""

    template_name = "finance/import.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", ImportForm())
        data = self.request.session.get(SESSION_KEY)
        if data and "form_errors" not in kwargs:
            result = importers.ParseResult.from_session(data)
            ctx["preview"] = importers.analyze(self.request.user, result)
            ctx["rows"] = result.rows
            ctx["errors"] = result.errors
            ctx["filename"] = data.get("filename", "")
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "cancel":
            request.session.pop(SESSION_KEY, None)
            return redirect("finance:import")
        if action == "confirm":
            data = request.session.pop(SESSION_KEY, None)
            if not data:
                messages.info(request, "Sube el archivo de nuevo.")
                return redirect("finance:import")
            result = importers.ParseResult.from_session(data)
            summary = importers.import_rows(
                request.user, result, recurring_refs=request.POST.getlist("recurring")
            )
            messages.success(
                request,
                f"Se importaron {summary['created']} movimientos"
                f" ({summary['skipped']} duplicados omitidos)"
                f" y {summary['recurrings']} recurrentes.",
            )
            return redirect("finance:accounts")

        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                result = importers.parse_neko_csv(form.cleaned_data["file"])
            except ValueError as exc:
                form.add_error("file", str(exc))
            else:
                if not result.rows:
                    form.add_error("file", "No se encontraron movimientos válidos.")
                else:
                    data = result.to_session()
                    data["filename"] = form.cleaned_data["file"].name
                    request.session[SESSION_KEY] = data
                    return redirect("finance:import")
        request.session.pop(SESSION_KEY, None)
        return self.render_to_response(self.get_context_data(form=form, form_errors=True))
