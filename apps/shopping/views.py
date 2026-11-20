from decimal import Decimal
from itertools import groupby
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.finance.templatetags.money import money

from .forms import CompleteForm, ItemForm, ProductForm, ShoppingListForm
from .models import AISLE_ORDER, Aisle, Item, Product, ShoppingList

SUGGESTIONS = 12


def _is_fetch(request):
    return request.headers.get("x-requested-with") == "fetch"


def _store_names(user):
    return (
        ShoppingList.objects.filter(owner=user)
        .exclude(store="")
        .values_list("store", flat=True)
        .distinct()
        .order_by("store")
    )


# ---------- Listas ----------


class HomeView(ListView):
    template_name = "shopping/home.html"
    context_object_name = "active_lists"

    def get_queryset(self):
        return (
            ShoppingList.objects.filter(owner=self.request.user, status=ShoppingList.Status.ACTIVE)
            .prefetch_related("items")
            .order_by("planned_date", "-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        for sl in context["active_lists"]:
            sl.summary = sl.totals()
        done = ShoppingList.objects.filter(owner=user, status=ShoppingList.Status.DONE)
        today = timezone.localdate()
        month = done.filter(
            completed_at__year=today.year, completed_at__month=today.month
        ).aggregate(total=Sum("total_paid"), count=Count("id"))
        month_total = month["total"] or Decimal("0")
        context.update(
            {
                "history": done.annotate(n_items=Count("items")).order_by("-completed_at")[:10],
                "month_total": month_total,
                "month_count": month["count"],
                "avg_ticket": (month_total / month["count"]) if month["count"] else None,
                "pending_items": Item.objects.filter(
                    shopping_list__owner=user,
                    shopping_list__status=ShoppingList.Status.ACTIVE,
                    is_checked=False,
                ).count(),
                "favorites": Product.objects.filter(owner=user, is_favorite=True).count(),
            }
        )
        return context


class ListOwnerMixin:
    def get_queryset(self):
        return ShoppingList.objects.filter(owner=self.request.user)


class ListFormMixin(ListOwnerMixin):
    form_class = ShoppingListForm
    template_name = "shopping/list_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stores"] = _store_names(self.request.user)
        return context

    def get_success_url(self):
        return reverse("shopping:detail", args=[self.object.pk])


class ListCreateView(ListFormMixin, CreateView):
    def get_initial(self):
        return {"planned_date": timezone.localdate()}

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, "Lista creada. Agrega tus artículos.")
        return super().form_valid(form)


class ListUpdateView(ListFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "Lista actualizada.")
        return super().form_valid(form)


class ListDeleteView(ListOwnerMixin, DeleteView):
    template_name = "shopping/confirm_delete.html"
    success_url = reverse_lazy("shopping:home")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["what"] = "esta lista"
        context["cancel_url"] = reverse("shopping:detail", args=[self.object.pk])
        return context

    def form_valid(self, form):
        messages.success(self.request, "Lista eliminada.")
        return super().form_valid(form)


def _aisle_groups(items):
    items = sorted(
        items, key=lambda i: (AISLE_ORDER.get(i.aisle, 99), i.is_checked, i.name.lower())
    )
    labels = dict(Aisle.choices)
    return [
        {"key": key, "label": labels.get(key, key), "items": list(group)}
        for key, group in groupby(items, key=lambda i: i.aisle)
    ]


def _render_detail(request, sl, form=None, status=200):
    items = list(sl.items.all())
    in_list = {i.name.lower() for i in items}
    products = Product.objects.filter(owner=request.user)
    suggestions = [
        p
        for p in products.order_by("-is_favorite", "-times_bought", "name")
        if p.name.lower() not in in_list
    ][:SUGGESTIONS]
    catalog = {
        p.name.lower(): {
            "aisle": p.aisle,
            "unit": p.unit,
            "price": str(p.last_price) if p.last_price is not None else "",
        }
        for p in products
    }
    context = {
        "list": sl,
        "groups": _aisle_groups(items),
        "summary": sl.totals(),
        "form": form or ItemForm(owner=request.user),
        "products": products,
        "catalog": catalog,
        "suggestions": suggestions,
        "finance_url": _finance_url(sl) if sl.is_done else "",
    }
    return render(request, "shopping/list_detail.html", context, status=status)


def _finance_url(sl):
    date = timezone.localtime(sl.completed_at).date() if sl.completed_at else timezone.localdate()
    concept = f"Súper {sl.store}".strip() if sl.store else sl.name
    params = {
        "tipo": "gasto",
        "monto": sl.total_paid or "",
        "concepto": concept,
        "categoria": "Supermercado,Súper,Despensa,Comida",
        "fecha": date.isoformat(),
        "next": reverse("shopping:detail", args=[sl.pk]),
    }
    return f"{reverse('finance:transaction_create')}?{urlencode(params)}"


def list_detail(request, pk):
    sl = get_object_or_404(ShoppingList, pk=pk, owner=request.user)
    return _render_detail(request, sl)


@require_POST
def item_add(request, pk):
    sl = get_object_or_404(ShoppingList, pk=pk, owner=request.user)
    if sl.is_done:
        messages.error(request, "Esta lista ya se completó. Usa «Repetir lista».")
        return redirect("shopping:detail", pk=sl.pk)
    form = ItemForm(request.POST, owner=request.user)
    if not form.is_valid():
        return _render_detail(request, sl, form=form, status=400)
    form.instance.shopping_list = sl
    item = form.save()
    messages.success(request, f"«{item.name}» agregado.")
    return redirect(f"{reverse('shopping:detail', args=[sl.pk])}#aisle-{item.aisle}")


@require_POST
def item_from_product(request, pk, product_pk):
    """Agrega con un clic un producto del catálogo (sugerencias)."""
    sl = get_object_or_404(ShoppingList, pk=pk, owner=request.user, status="activa")
    product = get_object_or_404(Product, pk=product_pk, owner=request.user)
    Item.objects.create(
        shopping_list=sl,
        product=product,
        name=product.name,
        unit=product.unit,
        aisle=product.aisle,
        price=product.last_price,
    )
    messages.success(request, f"«{product.name}» agregado.")
    return redirect("shopping:detail", pk=sl.pk)


def _summary_json(sl):
    s = sl.totals()
    return {
        "checked": s["checked"],
        "count": s["count"],
        "progress": s["progress"],
        "estimated": money(s["estimated"]),
        "in_cart": money(s["in_cart"]),
        "budget_left": money(s["budget_left"]) if s["budget_left"] is not None else "",
        "over_budget": s["over_budget"],
    }


@require_POST
def item_toggle(request, pk):
    item = get_object_or_404(
        Item.objects.select_related("shopping_list"),
        pk=pk,
        shopping_list__owner=request.user,
        shopping_list__status=ShoppingList.Status.ACTIVE,
    )
    item.is_checked = not item.is_checked
    item.save(update_fields=["is_checked"])
    return _item_response(request, item)


def _item_response(request, item):
    if _is_fetch(request):
        data = _summary_json(item.shopping_list)
        data.update(
            {
                "id": item.pk,
                "is_checked": item.is_checked,
                "subtotal": money(item.subtotal) if item.subtotal is not None else "",
            }
        )
        return JsonResponse(data)
    return redirect("shopping:detail", pk=item.shopping_list_id)


@require_POST
def item_price(request, pk):
    """Captura el precio real en el pasillo (campo en línea de cada artículo)."""
    item = get_object_or_404(
        Item.objects.select_related("shopping_list"),
        pk=pk,
        shopping_list__owner=request.user,
        shopping_list__status=ShoppingList.Status.ACTIVE,
    )
    raw = request.POST.get("price", "").strip().replace(",", ".")
    if raw == "":
        item.price = None
    else:
        try:
            price = Decimal(raw).quantize(Decimal("0.01"))
        except ArithmeticError:
            return JsonResponse({"error": "Precio inválido"}, status=400)
        if price < 0 or price >= Decimal("10000000000"):
            return JsonResponse({"error": "Precio inválido"}, status=400)
        item.price = price
    item.save(update_fields=["price"])
    return _item_response(request, item)


class ItemOwnerMixin:
    def get_queryset(self):
        return Item.objects.filter(shopping_list__owner=self.request.user)

    def get_success_url(self):
        return reverse("shopping:detail", args=[self.object.shopping_list_id])


class ItemUpdateView(ItemOwnerMixin, UpdateView):
    form_class = ItemForm
    template_name = "shopping/item_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Artículo actualizado.")
        return super().form_valid(form)


@require_POST
def item_delete(request, pk):
    item = get_object_or_404(Item, pk=pk, shopping_list__owner=request.user)
    sl = item.shopping_list
    item.delete()
    if _is_fetch(request):
        return JsonResponse(_summary_json(sl))
    messages.success(request, "Artículo eliminado.")
    return redirect("shopping:detail", pk=sl.pk)


def list_complete(request, pk):
    sl = get_object_or_404(ShoppingList, pk=pk, owner=request.user, status="activa")
    summary = sl.totals()
    form = CompleteForm(request.POST or None, initial={"total_paid": summary["in_cart"] or None})
    if request.method == "POST" and form.is_valid():
        pending = list(sl.items.filter(is_checked=False))
        sl.complete(form.cleaned_data["total_paid"])
        if form.cleaned_data["carry_over"] and pending:
            new = ShoppingList.objects.create(
                owner=request.user, name=f"Pendientes de {sl.name}", store=sl.store
            )
            for item in pending:
                item.pk = None
                item.shopping_list = new
                item.save()
            messages.info(request, f"{len(pending)} artículo(s) pasaron a «{new.name}».")
        messages.success(request, f"Compra terminada: {money(sl.total_paid)}.")
        return redirect("shopping:detail", pk=sl.pk)
    return render(
        request, "shopping/list_complete.html", {"list": sl, "summary": summary, "form": form}
    )


@require_POST
def list_duplicate(request, pk):
    """Repite una lista: mismos artículos, sin marcar y con los precios más recientes."""
    source = get_object_or_404(ShoppingList, pk=pk, owner=request.user)
    new = ShoppingList.objects.create(
        owner=request.user,
        name=source.name,
        store=source.store,
        budget=source.budget,
        planned_date=timezone.localdate(),
    )
    for item in source.items.select_related("product"):
        Item.objects.create(
            shopping_list=new,
            product=item.product,
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            aisle=item.aisle,
            price=item.product.last_price if item.product else item.price,
            note=item.note,
        )
    messages.success(request, "Lista repetida. Ajusta lo que necesites.")
    return redirect("shopping:detail", pk=new.pk)


# ---------- Catálogo de productos ----------


class ProductListView(ListView):
    template_name = "shopping/product_list.html"
    context_object_name = "products"
    paginate_by = 50

    def get_queryset(self):
        qs = Product.objects.filter(owner=self.request.user)
        q = self.request.GET.get("q", "").strip()
        aisle = self.request.GET.get("pasillo", "")
        if q:
            qs = qs.filter(name__icontains=q)
        if aisle in Aisle.values:
            qs = qs.filter(aisle=aisle)
        if self.request.GET.get("favoritos"):
            qs = qs.filter(is_favorite=True)
        return qs.order_by("-is_favorite", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        g = self.request.GET
        context.update(
            {
                "filters": {"q": g.get("q", ""), "pasillo": g.get("pasillo", "")},
                "only_favs": bool(g.get("favoritos")),
                "aisles": Aisle.choices,
            }
        )
        return context


class ProductOwnerMixin:
    success_url = reverse_lazy("shopping:products")

    def get_queryset(self):
        return Product.objects.filter(owner=self.request.user)


class ProductUpdateView(ProductOwnerMixin, UpdateView):
    form_class = ProductForm
    template_name = "shopping/product_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Producto actualizado.")
        return super().form_valid(form)


class ProductDeleteView(ProductOwnerMixin, DeleteView):
    template_name = "shopping/confirm_delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["what"] = "este producto del catálogo"
        context["cancel_url"] = reverse("shopping:products")
        return context

    def form_valid(self, form):
        messages.success(self.request, "Producto eliminado del catálogo.")
        return super().form_valid(form)


@require_POST
def product_favorite(request, pk):
    product = get_object_or_404(Product, pk=pk, owner=request.user)
    product.is_favorite = not product.is_favorite
    product.save(update_fields=["is_favorite"])
    if _is_fetch(request):
        return JsonResponse({"id": product.pk, "is_favorite": product.is_favorite})
    return redirect(request.POST.get("next") or "shopping:products")


@require_POST
def favorites_to_list(request, pk):
    """Agrega todos los favoritos que aún no están en la lista."""
    sl = get_object_or_404(ShoppingList, pk=pk, owner=request.user, status="activa")
    in_list = {n.lower() for n in sl.items.values_list("name", flat=True)}
    added = 0
    for p in Product.objects.filter(owner=request.user, is_favorite=True):
        if p.name.lower() in in_list:
            continue
        Item.objects.create(
            shopping_list=sl, product=p, name=p.name, unit=p.unit, aisle=p.aisle, price=p.last_price
        )
        added += 1
    if added:
        messages.success(request, f"{added} favorito(s) agregados.")
    else:
        messages.info(request, "Tus favoritos ya están en la lista.")
    return redirect("shopping:detail", pk=sl.pk)
