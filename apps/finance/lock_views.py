from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import security

MIN_LENGTH = 4


class SetupForm(forms.Form):
    password1 = forms.CharField(
        label="Nueva contraseña de Finanzas",
        min_length=MIN_LENGTH,
        max_length=64,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "placeholder": f"Mínimo {MIN_LENGTH} caracteres"}
        ),
    )
    password2 = forms.CharField(
        label="Confírmala",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password1") != data.get("password2"):
            self.add_error("password2", "Las contraseñas no coinciden.")
        return data


class ChangeForm(SetupForm):
    """Cambiar requiere la actual de Finanzas o, si la olvidaste, la de tu cuenta."""

    current = forms.CharField(
        label="Contraseña actual de Finanzas (o la de tu cuenta CRIS si la olvidaste)",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    field_order = ["current", "password1", "password2"]


class UnlockForm(forms.Form):
    password = forms.CharField(
        label="Contraseña de Finanzas",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "off", "autofocus": True, "placeholder": "••••••"}
        ),
    )


def _next(request):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}):
        return target
    return reverse("finance:home")


def lock_setup(request):
    """Crear la contraseña (primera vez) o cambiarla."""
    lock_obj = security.get_lock(request.user)
    form_class = ChangeForm if lock_obj else SetupForm
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if lock_obj:
            current = form.cleaned_data["current"]
            # La contraseña de la cuenta sirve para restablecer si se olvidó la de Finanzas.
            if not request.user.check_password(current):
                ok, error = security.verify(lock_obj, current)
                if not ok:
                    form.add_error("current", error)
                    return render(
                        request,
                        "finance/lock_setup.html",
                        {"form": form, "is_change": True, "next": _next(request)},
                    )
        security.set_password(request.user, form.cleaned_data["password1"])
        security.unlock(request)
        messages.success(
            request, "Contraseña de Finanzas actualizada." if lock_obj else "Finanzas protegido."
        )
        return redirect(_next(request))
    return render(
        request,
        "finance/lock_setup.html",
        {"form": form, "is_change": bool(lock_obj), "next": _next(request)},
    )


def unlock(request):
    lock_obj = security.get_lock(request.user)
    if not lock_obj:
        return redirect("finance:lock_setup")
    if security.is_unlocked(request):
        return redirect(_next(request))
    form = UnlockForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ok, error = security.verify(lock_obj, form.cleaned_data["password"])
        if ok:
            security.unlock(request)
            return redirect(_next(request))
        form.add_error("password", error)
    return render(
        request,
        "finance/unlock.html",
        {
            "form": form,
            "next": _next(request),
            "minutes": security.idle_minutes(),
            "cooldown": security.remaining_cooldown(lock_obj),
        },
    )


@require_POST
def lock_now(request):
    security.lock(request)
    messages.info(request, "Finanzas bloqueado.")
    return redirect("core:dashboard")
