from django.urls import path

from . import views

app_name = "shopping"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("nueva/", views.ListCreateView.as_view(), name="create"),
    path("<int:pk>/", views.list_detail, name="detail"),
    path("<int:pk>/editar/", views.ListUpdateView.as_view(), name="update"),
    path("<int:pk>/eliminar/", views.ListDeleteView.as_view(), name="delete"),
    path("<int:pk>/terminar/", views.list_complete, name="complete"),
    path("<int:pk>/repetir/", views.list_duplicate, name="duplicate"),
    path("<int:pk>/articulos/", views.item_add, name="item_add"),
    path("<int:pk>/favoritos/", views.favorites_to_list, name="favorites_to_list"),
    path("<int:pk>/agregar/<int:product_pk>/", views.item_from_product, name="item_from_product"),
    path("articulo/<int:pk>/editar/", views.ItemUpdateView.as_view(), name="item_update"),
    path("articulo/<int:pk>/eliminar/", views.item_delete, name="item_delete"),
    path("articulo/<int:pk>/carrito/", views.item_toggle, name="item_toggle"),
    path("articulo/<int:pk>/precio/", views.item_price, name="item_price"),
    path("productos/", views.ProductListView.as_view(), name="products"),
    path("productos/<int:pk>/editar/", views.ProductUpdateView.as_view(), name="product_update"),
    path("productos/<int:pk>/eliminar/", views.ProductDeleteView.as_view(), name="product_delete"),
    path("productos/<int:pk>/favorito/", views.product_favorite, name="product_favorite"),
]
