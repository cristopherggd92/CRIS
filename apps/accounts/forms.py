from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, label="Recordarme")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Usuario",
                "autocomplete": "username",
                "autocapitalize": "characters",
                "class": "input-upper",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "placeholder": "Contraseña",
                "autocomplete": "current-password",
            }
        )

    def clean_username(self):
        """Permite escribir el usuario en mayúsculas o minúsculas.

        Busca el usuario sin distinguir mayúsculas y devuelve el nombre tal
        como está registrado, para que authenticate() lo encuentre.
        """
        username = self.cleaned_data.get("username", "")
        matches = list(
            get_user_model()
            .objects.filter(username__iexact=username)
            .values_list("username", flat=True)[:2]
        )
        if len(matches) == 1:
            return matches[0]
        return username  # 0 coincidencias o ambiguo: se valida tal cual


class PasswordChangeForm(auth_forms.PasswordChangeForm):
    """Igual al de Django, con placeholders y autocompletado correctos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update(
            {"autocomplete": "current-password", "placeholder": "Tu contraseña actual"}
        )
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password1"].widget.attrs["placeholder"] = "Mínimo 10 caracteres"
        self.fields["new_password2"].widget.attrs["placeholder"] = "Repite la nueva contraseña"
