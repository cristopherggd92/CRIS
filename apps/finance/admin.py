from django.contrib import admin

from .models import Account, Category, Recurring, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "type", "initial_balance", "is_archived"]
    list_filter = ["type", "is_archived"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "kind", "color"]
    list_filter = ["kind"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["date", "kind", "amount", "account", "to_account", "category", "description"]
    list_filter = ["kind", "account", "category"]
    search_fields = ["description"]
    date_hierarchy = "date"


@admin.register(Recurring)
class RecurringAdmin(admin.ModelAdmin):
    list_display = ["description", "kind", "amount", "frequency", "next_date", "is_active"]
    list_filter = ["kind", "frequency", "is_active"]
