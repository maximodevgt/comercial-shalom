from django.conf import settings
from django.db import models


class Venta(models.Model):
    """Una venta del POS. Los totales son SIEMPRE recalculados en el backend
    (regla de oro #3); nunca se confía en montos del frontend."""

    class MetodoPago(models.TextChoices):
        EFECTIVO = 'efectivo', 'Efectivo'
        TARJETA = 'tarjeta', 'Tarjeta'

    class Estado(models.TextChoices):
        COMPLETADA = 'completada', 'Completada'
        ANULADA = 'anulada', 'Anulada'

    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='ventas',
    )
    # Para consumidor final con nombre (sin cliente registrado).
    nombre_cliente_libre = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=30, blank=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ventas',
        verbose_name='cajero',
    )

    metodo_pago = models.CharField(
        max_length=10, choices=MetodoPago.choices, default=MetodoPago.EFECTIVO)
    monto_tarjeta = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)

    saldo_aplicado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.COMPLETADA)
    motivo_anulacion = models.TextField(blank=True, null=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'venta'
        verbose_name_plural = 'ventas'
        ordering = ('-creado',)
        indexes = [
            models.Index(fields=['-creado']),
            models.Index(fields=['estado']),
        ]

    def __str__(self):
        return f'Venta #{self.pk}'

    @property
    def nombre_cliente(self):
        if self.cliente:
            return self.cliente.nombre
        return self.nombre_cliente_libre or 'Consumidor Final'

    @property
    def cantidad_total(self):
        return sum(d.cantidad for d in self.detalles.all())

    @property
    def esta_anulada(self):
        return self.estado == self.Estado.ANULADA


class DetalleVenta(models.Model):
    """Línea de una venta. Guarda el precio original (de BD al momento) y el
    precio efectivamente cobrado, para rastrear descuentos."""

    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('productos.Producto', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_original = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'detalle de venta'
        verbose_name_plural = 'detalles de venta'

    def __str__(self):
        return f'{self.cantidad}x {self.producto.nombre_completo}'

    @property
    def descuento(self):
        return (self.precio_original - self.precio_unitario) * self.cantidad
