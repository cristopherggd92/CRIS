from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.finance.models import Category, ensure_default_categories
from apps.shopping.models import Aisle, Item, Product, ShoppingList

D = Decimal
FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="cris", password="clave-segura-123")


@pytest.fixture
def logged(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def sl(user):
    return ShoppingList.objects.create(
        owner=user, name="Despensa", store="Soriana", budget=D("500")
    )


def add(client, sl, **data):
    payload = {"name": "Leche", "quantity": "1", "unit": "l", "aisle": "lacteos", "price": ""}
    payload.update(data)
    return client.post(reverse("shopping:item_add", args=[sl.pk]), payload)


# ---------- Menú ----------


def test_menu_muestra_compras_y_no_notas_ni_habitos(logged):
    html = logged.get(reverse("core:dashboard")).content.decode()
    assert reverse("shopping:home") in html
    assert "Notas" not in html and "Hábitos" not in html


def test_compras_requiere_login(client, db):
    response = client.get(reverse("shopping:home"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


# ---------- Listas ----------


def test_crear_lista(logged, user):
    response = logged.post(
        reverse("shopping:create"), {"name": "Súper semanal", "store": "Walmart", "budget": "800"}
    )
    sl = ShoppingList.objects.get(owner=user)
    assert response.url == reverse("shopping:detail", args=[sl.pk])
    assert sl.status == ShoppingList.Status.ACTIVE


def test_no_puedo_ver_listas_de_otro(client, sl):
    otro = get_user_model().objects.create_user(username="otro", password="x-clave-123")
    client.force_login(otro)
    assert client.get(reverse("shopping:detail", args=[sl.pk])).status_code == 404
    assert client.post(reverse("shopping:delete", args=[sl.pk])).status_code == 404


def test_inicio_muestra_lista_activa_con_avance(logged, sl):
    Item.objects.create(shopping_list=sl, name="Pan", price=D("40"), is_checked=True)
    Item.objects.create(shopping_list=sl, name="Huevo", price=D("60"))
    html = logged.get(reverse("shopping:home")).content.decode()
    assert "Despensa" in html
    assert "1/2" in html
    assert "$100.00" in html  # estimado


# ---------- Artículos y catálogo ----------


def test_agregar_articulo_crea_producto_en_catalogo(logged, user, sl):
    response = add(logged, sl, name="  Leche   entera ", price="28.50", quantity="2")
    assert response.status_code == 302
    item = sl.items.get()
    assert item.name == "Leche entera"
    assert item.subtotal == D("57.00")
    product = Product.objects.get(owner=user)
    assert product.name == "Leche entera" and product.last_price == D("28.50")


def test_mismo_producto_no_se_duplica_sin_importar_mayusculas(logged, user, sl):
    add(logged, sl, name="Tortillas", aisle="panaderia")
    add(logged, sl, name="TORTILLAS", aisle="panaderia")
    assert Product.objects.filter(owner=user).count() == 1


def test_articulo_invalido_muestra_errores(logged, sl):
    response = add(logged, sl, name="", quantity="0")
    assert response.status_code == 400
    assert not sl.items.exists()


def test_articulos_agrupados_por_pasillo_en_orden(logged, sl):
    add(logged, sl, name="Jabón", aisle="limpieza")
    add(logged, sl, name="Manzana", aisle="frutas")
    html = logged.get(reverse("shopping:detail", args=[sl.pk])).content.decode()
    assert html.index("Frutas y verduras") < html.index("Limpieza del hogar")


def test_marcar_articulo_actualiza_totales_por_fetch(logged, sl):
    item = Item.objects.create(shopping_list=sl, name="Queso", quantity=2, price=D("80"))
    data = logged.post(reverse("shopping:item_toggle", args=[item.pk]), **FETCH).json()
    assert data["is_checked"] is True
    assert data["in_cart"] == "$160.00"
    assert data["progress"] == 100
    item.refresh_from_db()
    assert item.is_checked


def test_capturar_precio_en_linea(logged, sl):
    item = Item.objects.create(shopping_list=sl, name="Café", quantity=3)
    data = logged.post(
        reverse("shopping:item_price", args=[item.pk]), {"price": "99,90"}, **FETCH
    ).json()
    assert data["subtotal"] == "$299.70"
    assert data["estimated"] == "$299.70"
    bad = logged.post(reverse("shopping:item_price", args=[item.pk]), {"price": "abc"}, **FETCH)
    assert bad.status_code == 400


def test_presupuesto_rebasado(sl):
    Item.objects.create(shopping_list=sl, name="Carne", quantity=2, price=D("300"))
    summary = sl.totals()
    assert summary["over_budget"] is True
    assert summary["budget_left"] == D("-100")


def test_eliminar_articulo(logged, sl):
    item = Item.objects.create(shopping_list=sl, name="Atún", price=D("20"))
    data = logged.post(reverse("shopping:item_delete", args=[item.pk]), **FETCH).json()
    assert data["count"] == 0
    assert not Item.objects.exists()


def test_sugerencias_y_favoritos(logged, user, sl):
    fav = Product.objects.create(owner=user, name="Plátano", aisle=Aisle.PRODUCE, is_favorite=True)
    Product.objects.create(owner=user, name="Arroz", aisle=Aisle.PANTRY, times_bought=5)
    html = logged.get(reverse("shopping:detail", args=[sl.pk])).content.decode()
    assert "Plátano" in html and "Arroz" in html
    logged.post(reverse("shopping:favorites_to_list", args=[sl.pk]))
    logged.post(reverse("shopping:favorites_to_list", args=[sl.pk]))  # no duplica
    assert list(sl.items.values_list("product", flat=True)) == [fav.pk]


def test_agregar_desde_sugerencia_usa_ultimo_precio(logged, user, sl):
    p = Product.objects.create(owner=user, name="Frijol", aisle=Aisle.PANTRY, last_price=D("35"))
    logged.post(reverse("shopping:item_from_product", args=[sl.pk, p.pk]))
    item = sl.items.get()
    assert item.price == D("35") and item.aisle == Aisle.PANTRY


# ---------- Terminar, repetir y Finanzas ----------


def test_terminar_compra_guarda_precios_y_tendencia(logged, user, sl):
    p = Product.objects.create(owner=user, name="Aceite", last_price=D("40"))
    Item.objects.create(shopping_list=sl, product=p, name="Aceite", price=D("45"), is_checked=True)
    Item.objects.create(shopping_list=sl, name="Sal", price=D("10"))  # no se encontró
    response = logged.post(reverse("shopping:complete", args=[sl.pk]), {"carry_over": "on"})
    assert response.url == reverse("shopping:detail", args=[sl.pk])
    sl.refresh_from_db()
    p.refresh_from_db()
    assert sl.status == ShoppingList.Status.DONE
    assert sl.total_paid == D("45.00")
    assert (p.last_price, p.prev_price, p.times_bought) == (D("45"), D("40"), 1)
    assert p.price_trend == "up" and p.price_change_pct == D("12.5")
    assert p.last_store == "Soriana"
    nueva = ShoppingList.objects.get(status=ShoppingList.Status.ACTIVE)
    assert list(nueva.items.values_list("name", flat=True)) == ["Sal"]


def test_terminar_con_total_de_ticket(logged, sl):
    Item.objects.create(shopping_list=sl, name="Pan", price=D("40"), is_checked=True)
    logged.post(reverse("shopping:complete", args=[sl.pk]), {"total_paid": "38.90"})
    sl.refresh_from_db()
    assert sl.total_paid == D("38.90")


def test_lista_terminada_no_acepta_cambios(logged, sl):
    item = Item.objects.create(shopping_list=sl, name="Pan", is_checked=True)
    sl.complete()
    add(logged, sl, name="Otro")
    assert sl.items.count() == 1
    assert logged.post(reverse("shopping:item_toggle", args=[item.pk])).status_code == 404


def test_repetir_lista_con_precios_recientes(logged, user, sl):
    p = Product.objects.create(owner=user, name="Huevo", last_price=D("65"))
    Item.objects.create(
        shopping_list=sl, product=p, name="Huevo", quantity=2, price=D("60"), is_checked=True
    )
    sl.complete()
    logged.post(reverse("shopping:duplicate", args=[sl.pk]))
    nueva = ShoppingList.objects.exclude(pk=sl.pk).get()
    item = nueva.items.get()
    assert nueva.status == ShoppingList.Status.ACTIVE
    assert (item.is_checked, item.quantity, item.price) == (False, 2, D("60"))


def test_boton_registrar_gasto_precarga_finanzas(logged, user, sl, unlock_finance):
    ensure_default_categories(user)
    unlock_finance(logged, user)
    Item.objects.create(shopping_list=sl, name="Pan", price=D("120"), is_checked=True)
    sl.complete()
    html = logged.get(reverse("shopping:detail", args=[sl.pk])).content.decode()
    assert "Registrar gasto en Finanzas" in html
    url = (
        reverse("finance:transaction_create")
        + "?tipo=gasto&monto=120.00&concepto=S%C3%BAper+Soriana&categoria=Supermercado,Comida"
    )
    form = logged.get(url).context["form"]
    assert form.initial["amount"] == D("120.00")
    assert form.initial["description"] == "Súper Soriana"
    assert form.initial["category"].name == "Comida"  # no existe "Supermercado"
    Category.objects.create(owner=user, kind="gasto", name="Supermercado")
    assert logged.get(url).context["form"].initial["category"].name == "Supermercado"


# ---------- Catálogo ----------


def test_catalogo_filtra_y_marca_favorito(logged, user):
    p = Product.objects.create(owner=user, name="Jabón", aisle=Aisle.CLEANING)
    Product.objects.create(owner=user, name="Manzana", aisle=Aisle.PRODUCE)
    html = logged.get(reverse("shopping:products") + "?pasillo=limpieza").content.decode()
    assert "Jabón" in html and "Manzana" not in html
    logged.post(reverse("shopping:product_favorite", args=[p.pk]))
    p.refresh_from_db()
    assert p.is_favorite


def test_editar_producto_valida_nombre_repetido(logged, user):
    Product.objects.create(owner=user, name="Leche")
    p = Product.objects.create(owner=user, name="Yogurt")
    response = logged.post(
        reverse("shopping:product_update", args=[p.pk]),
        {"name": "leche", "aisle": "lacteos", "unit": "pza"},
    )
    assert response.status_code == 200
    assert "Ya tienes un producto" in response.content.decode()
