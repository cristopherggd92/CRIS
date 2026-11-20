from django.contrib import admin

from .models import Item, Product, ShoppingList


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "store", "status", "planned_date", "total_paid")
    list_filter = ("status",)
    inlines = [ItemInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "aisle", "last_price", "times_bought", "is_favorite")
    list_filter = ("aisle", "is_favorite")
    search_fields = ("name",)
