from django.urls import path

from . import views

app_name = "household"

urlpatterns = [
    path("", views.home, name="home"),
    path("servicios/", views.services_page, name="services"),
    path("vehiculos/", views.vehicles_page, name="vehicles"),
    path("mantenimiento/", views.maintenance_page, name="maintenance"),
    path("agenda/", views.agenda_page, name="agenda"),
    path("inventario/", views.inventory_page, name="inventory"),
    path("nuevo/<str:kind>/", views.form_view, name="form_new"),
    path("editar/<str:kind>/<int:pk>/", views.form_view, name="form_edit"),
    path("eliminar/<str:kind>/<int:pk>/", views.delete_view, name="delete"),
    path("recibos/<int:pk>/pagar/", views.bill_pay, name="bill_pay"),
    path("servicios/<int:pk>/pagar/", views.service_pay, name="service_pay"),
    path("agenda/<int:pk>/hecho/", views.reminder_done, name="reminder_done"),
    path("vehiculos/<int:pk>/km/", views.vehicle_km, name="vehicle_km"),
]
