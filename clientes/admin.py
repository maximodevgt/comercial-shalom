from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'saldo_favor', 'creado')
    search_fields = ('nombre', 'telefono')
    readonly_fields = ('saldo_favor',)
