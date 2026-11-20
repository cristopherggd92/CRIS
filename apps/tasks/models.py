from datetime import timedelta
from zlib import crc32

from django.conf import settings
from django.db import models
from django.utils import timezone

TAG_COLORS = ["indigo", "emerald", "amber", "rose", "sky", "violet", "teal", "orange"]


class Tag(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags"
    )
    name = models.CharField("nombre", max_length=40)
    color = models.CharField(max_length=20, default="indigo")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_tag_per_owner"),
        ]
        verbose_name = "etiqueta"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk:
            # Color estable según el nombre: "trabajo" siempre sale del mismo color
            self.color = TAG_COLORS[crc32(self.name.encode()) % len(TAG_COLORS)]
        super().save(*args, **kwargs)


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "pendiente", "Pendiente"
        IN_PROGRESS = "en_progreso", "En progreso"
        DONE = "completada", "Completada"

    class Priority(models.IntegerChoices):
        LOW = 1, "Baja"
        MEDIUM = 2, "Media"
        HIGH = 3, "Alta"
        URGENT = 4, "Urgente"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField("nombre de la tarea", max_length=200)
    description = models.TextField("descripción", blank=True)
    status = models.CharField(
        "estatus", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    priority = models.PositiveSmallIntegerField(
        "prioridad", choices=Priority.choices, default=Priority.MEDIUM
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="tasks", verbose_name="etiquetas")
    created_at = models.DateTimeField("fecha de registro", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField("fecha de vencimiento", null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-priority", "due_date", "-created_at"]
        verbose_name = "tarea"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status == self.Status.DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != self.Status.DONE:
            self.completed_at = None
        super().save(*args, **kwargs)

    @property
    def due_state(self):
        """overdue | today | soon | None. Sirve para pintar la fecha de color."""
        if not self.due_date or self.status == self.Status.DONE:
            return None
        today = timezone.localdate()
        if self.due_date < today:
            return "overdue"
        if self.due_date == today:
            return "today"
        if self.due_date <= today + timedelta(days=3):
            return "soon"
        return None

    @property
    def is_overdue(self):
        return self.due_state == "overdue"
