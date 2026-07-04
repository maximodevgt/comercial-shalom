from django.contrib import admin

from .models import DetalleVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ('producto', 'cantidad', 'precio_original', 'precio_unitario', 'subtotal')
    can_delete = False


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre_cliente', 'usuario', 'total', 'metodo_pago', 'estado', 'creado')
    list_filter = ('estado', 'metodo_pago', 'creado')
    search_fields = ('id', 'nombre_cliente_libre', 'cliente__nombre')
    readonly_fields = (
        'cliente', 'nombre_cliente_libre', 'telefono', 'usuario', 'metodo_pago',
        'monto_tarjeta', 'saldo_aplicado', 'subtotal', 'descuento_total', 'total',
        'estado', 'motivo_anulacion', 'creado',
    )
    inlines = [DetalleVentaInline]
