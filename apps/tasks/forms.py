from django import forms

from .models import Tag, Task

MAX_TAGS = 10


class TaskForm(forms.ModelForm):
    tags_text = forms.CharField(
        label="Etiquetas",
        required=False,
        help_text="Sepáralas con comas. Ej.: trabajo, casa, urgente",
        widget=forms.TextInput(attrs={"placeholder": "trabajo, personal"}),
    )

    class Meta:
        model = Task
        fields = ["title", "description", "status", "priority", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "¿Qué tienes que hacer?"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Detalles (opcional)"}),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["tags_text"].initial = ", ".join(t.name for t in self.instance.tags.all())

    def clean_tags_text(self):
        raw = self.cleaned_data["tags_text"]
        names = []
        for part in raw.split(","):
            name = part.strip().lower()
            if not name:
                continue
            if len(name) > 40:
                raise forms.ValidationError(f'La etiqueta "{name[:20]}…" es muy larga.')
            if name not in names:
                names.append(name)
        if len(names) > MAX_TAGS:
            raise forms.ValidationError(f"Máximo {MAX_TAGS} etiquetas por tarea.")
        return names

    def save(self, commit=True):
        task = super().save(commit=False)
        task.owner = self.owner
        if commit:
            task.save()
            tags = [
                Tag.objects.get_or_create(owner=self.owner, name=name)[0]
                for name in self.cleaned_data["tags_text"]
            ]
            task.tags.set(tags)
        return task
