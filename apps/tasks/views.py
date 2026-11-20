from django.contrib import messages
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import TaskForm
from .models import Task

SORT_OPTIONS = {
    "vencimiento": ("Vencimiento", ["due_date", "-priority"]),
    "prioridad": ("Prioridad", ["-priority", "due_date"]),
    "recientes": ("Más recientes", ["-created_at"]),
}


class OwnerQuerysetMixin:
    """Cada usuario solo ve y modifica sus propias tareas."""

    def get_queryset(self):
        return Task.objects.filter(owner=self.request.user).prefetch_related("tags")


class TaskListView(OwnerQuerysetMixin, ListView):
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 20

    def get_filters(self):
        g = self.request.GET
        return {
            "q": g.get("q", "").strip(),
            "status": g.get("status", ""),
            "priority": g.get("priority", ""),
            "tag": g.get("tag", ""),
            "sort": g.get("sort", "") if g.get("sort") in SORT_OPTIONS else "",
        }

    def get_queryset(self):
        qs = super().get_queryset()
        f = self.get_filters()
        if f["q"]:
            qs = qs.filter(Q(title__icontains=f["q"]) | Q(description__icontains=f["q"]))
        if f["status"] == "vencidas":
            qs = qs.exclude(status=Task.Status.DONE).filter(due_date__lt=timezone.localdate())
        elif f["status"] in Task.Status.values:
            qs = qs.filter(status=f["status"])
        if f["priority"].isdigit():
            qs = qs.filter(priority=int(f["priority"]))
        if f["tag"]:
            qs = qs.filter(tags__name=f["tag"])
        if f["sort"]:
            qs = qs.order_by(*SORT_OPTIONS[f["sort"]][1])
        else:
            # Por defecto: en progreso, luego pendientes y al final las completadas
            qs = qs.annotate(
                status_rank=Case(
                    When(status=Task.Status.IN_PROGRESS, then=Value(0)),
                    When(status=Task.Status.PENDING, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            ).order_by("status_rank", "-priority", "due_date", "-created_at")
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_tasks = Task.objects.filter(owner=self.request.user)
        counts = user_tasks.aggregate(
            total=Count("id"),
            pendiente=Count("id", filter=Q(status=Task.Status.PENDING)),
            en_progreso=Count("id", filter=Q(status=Task.Status.IN_PROGRESS)),
            completada=Count("id", filter=Q(status=Task.Status.DONE)),
            vencidas=Count(
                "id",
                filter=~Q(status=Task.Status.DONE) & Q(due_date__lt=timezone.localdate()),
            ),
        )
        filters = self.get_filters()
        query = self.request.GET.copy()
        query.pop("page", None)
        context.update(
            {
                "counts": counts,
                "filters": filters,
                "has_filters": any(filters.values()),
                "querystring": query.urlencode(),
                "status_choices": Task.Status.choices,
                "priority_choices": Task.Priority.choices,
                "sort_options": [(k, v[0]) for k, v in SORT_OPTIONS.items()],
                "user_tags": self.request.user.tags.all(),
            }
        )
        return context


class TaskFormMixin(OwnerQuerysetMixin):
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("tasks:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs


class TaskCreateView(TaskFormMixin, CreateView):
    def form_valid(self, form):
        messages.success(self.request, "Tarea creada.")
        return super().form_valid(form)


class TaskUpdateView(TaskFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "Tarea actualizada.")
        return super().form_valid(form)


class TaskDeleteView(OwnerQuerysetMixin, DeleteView):
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("tasks:list")

    def form_valid(self, form):
        messages.success(self.request, "Tarea eliminada.")
        return super().form_valid(form)


@require_POST
def task_set_status(request, pk):
    """Cambia el estatus. Responde JSON si la petición viene de JavaScript."""
    task = get_object_or_404(Task, pk=pk, owner=request.user)
    status = request.POST.get("status")
    if status not in Task.Status.values:
        return JsonResponse({"error": "Estatus inválido"}, status=400)
    task.status = status
    task.save()
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse(
            {
                "id": task.pk,
                "status": task.status,
                "status_label": task.get_status_display(),
                "due_state": task.due_state or "",
            }
        )
    return redirect(request.POST.get("next") or "tasks:list")
