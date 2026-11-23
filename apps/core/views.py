from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.generic import TemplateView

from .modules import MODULES


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modules"] = MODULES
        return context


@login_not_required
def health(request):
    return JsonResponse({"status": "ok"})
