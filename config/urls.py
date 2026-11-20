from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuenta/", include("apps.accounts.urls")),
    path("tareas/", include("apps.tasks.urls")),
    path("finanzas/", include("apps.finance.urls")),
    path("compras/", include("apps.shopping.urls")),
    path("hogar/", include("apps.household.urls")),
    path("", include("apps.core.urls")),
]
