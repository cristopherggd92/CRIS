from django.conf import settings
from django.contrib import admin
from django.urls import include, path

# Módulos que se pueden apagar con DISABLED_MODULES (ver config/settings/base.py)
MODULE_URLS = [
    ("tasks", "tareas/", "apps.tasks.urls"),
    ("finance", "finanzas/", "apps.finance.urls"),
    ("shopping", "compras/", "apps.shopping.urls"),
    ("household", "hogar/", "apps.household.urls"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuenta/", include("apps.accounts.urls")),
    *[
        path(prefix, include(module))
        for key, prefix, module in MODULE_URLS
        if key not in settings.DISABLED_MODULES
    ],
    path("", include("apps.core.urls")),
]
