from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.TaskListView.as_view(), name="list"),
    path("nueva/", views.TaskCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", views.TaskUpdateView.as_view(), name="update"),
    path("<int:pk>/eliminar/", views.TaskDeleteView.as_view(), name="delete"),
    path("<int:pk>/estatus/", views.task_set_status, name="set_status"),
]
