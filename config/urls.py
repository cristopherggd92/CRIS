from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuenta/", include("apps.accounts.urls")),
    path("tareas/", include("apps.tasks.urls")),
    path("", include("apps.core.urls")),
]
