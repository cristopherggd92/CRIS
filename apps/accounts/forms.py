from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, label="Recordarme")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Usuario", "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {
                "placeholder": "Contraseña",
                "autocomplete": "current-password",
            }
        )