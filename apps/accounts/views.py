from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from .forms import LoginForm, PasswordChangeForm


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        # Sin "Recordarme" la sesión termina al cerrar el navegador
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        return super().form_valid(form)


class LogoutView(auth_views.LogoutView):
    pass


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("core:dashboard")

    def form_valid(self, form):
        messages.success(self.request, "Contraseña actualizada.")
        return super().form_valid(form)
