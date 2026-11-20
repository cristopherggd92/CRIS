from django.contrib import admin

from .models import Tag, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "status", "priority", "due_date", "created_at"]
    list_filter = ["status", "priority", "tags"]
    search_fields = ["title", "description"]
    filter_horizontal = ["tags"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "color"]
    search_fields = ["name"]
