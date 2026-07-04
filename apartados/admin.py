from django.contrib import admin

from .models import Abono, Apartado


class AbonoInline(admin.TabularInline):
    model = Abono
    extra = 0
    readonly_fields = ('monto', 'metodo', 'usuario', 'creado')
    can_delete = False


@admin.register(Apartado)
class ApartadoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre_cliente', 'producto', 'precio_total', 'estado', 'creado')
    list_filter = ('estado',)
    search_fields = ('id', 'nombre_cliente_libre', 'cliente__nombre')
    readonly_fields = ('precio_original', 'venta')
    inlines = [AbonoInline]
