from django.urls import path

from . import lock_views, views

app_name = "finance"

urlpatterns = [
    path("", views.FinanceHomeView.as_view(), name="home"),
    path("desbloquear/", lock_views.unlock, name="unlock"),
    path("candado/", lock_views.lock_setup, name="lock_setup"),
    path("bloquear/", lock_views.lock_now, name="lock"),
    path("movimientos/", views.TransactionListView.as_view(), name="transactions"),
    path("movimientos/nuevo/", views.TransactionCreateView.as_view(), name="transaction_create"),
    path(
        "movimientos/<int:pk>/editar/",
        views.TransactionUpdateView.as_view(),
        name="transaction_update",
    ),
    path(
        "movimientos/<int:pk>/eliminar/",
        views.TransactionDeleteView.as_view(),
        name="transaction_delete",
    ),
    path("cuentas/", views.AccountListView.as_view(), name="accounts"),
    path("cuentas/nueva/", views.AccountCreateView.as_view(), name="account_create"),
    path("cuentas/<int:pk>/editar/", views.AccountUpdateView.as_view(), name="account_update"),
    path("cuentas/<int:pk>/eliminar/", views.AccountDeleteView.as_view(), name="account_delete"),
    path("recurrentes/", views.RecurringListView.as_view(), name="recurring"),
    path("recurrentes/nueva/", views.RecurringCreateView.as_view(), name="recurring_create"),
    path(
        "recurrentes/<int:pk>/editar/", views.RecurringUpdateView.as_view(), name="recurring_update"
    ),
    path(
        "recurrentes/<int:pk>/eliminar/",
        views.RecurringDeleteView.as_view(),
        name="recurring_delete",
    ),
    path("recurrentes/<int:pk>/pausar/", views.recurring_toggle, name="recurring_toggle"),
    path("importar/", views.ImportView.as_view(), name="import"),
    path("categorias/", views.CategoryListView.as_view(), name="categories"),
    path("categorias/nueva/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categorias/<int:pk>/editar/", views.CategoryUpdateView.as_view(), name="category_update"),
    path(
        "categorias/<int:pk>/eliminar/", views.CategoryDeleteView.as_view(), name="category_delete"
    ),
]
