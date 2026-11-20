from django.contrib.auth import views as auth_views

from .forms import LoginForm


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