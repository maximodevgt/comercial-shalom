from decimal import Decimal

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
        # Defensa en profundidad (B-10): los invariantes de dinero quedan
        # garantizados también a nivel de BD (la capa de servicio ya valida).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total__gte=0),
                name='venta_total_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name='venta_subtotal_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(saldo_aplicado__gte=0),
                name='venta_saldo_aplicado_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(descuento_total__gte=0),
                name='venta_descuento_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(monto_tarjeta__isnull=True) | models.Q(monto_tarjeta__gte=0),
                name='venta_monto_tarjeta_no_negativo'),
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

    @property
    def ajuste_tarjeta(self):
        """Diferencia entre lo que cobró el POS del banco y el total calculado
        de las líneas (solo ventas con tarjeta, donde el monto de la terminal
        ES el total). Positivo = se cobró de más (p. ej. recargo por tarjeta);
        negativo = rebaja. Derivado: total − (subtotal − saldo_aplicado)."""
        if self.metodo_pago != self.MetodoPago.TARJETA:
            return Decimal('0.00')
        esperado = self.subtotal - self.saldo_aplicado
        return (self.total - esperado).quantize(Decimal('0.01'))

    @property
    def ajuste_tarjeta_abs(self):
        """Valor absoluto del ajuste (los templates lo muestran con su signo)."""
        return abs(self.ajuste_tarjeta)

    @property
    def es_de_liquidacion(self):
        """True si esta venta se generó al liquidar un apartado.

        El reverse `apartado_origen` es un queryset (FK con related_name);
        una venta normal no tiene apartado de origen → exists() es False.
        Estas ventas no se anulan (se corrigen desde el apartado)."""
        return self.apartado_origen.exists()


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
        # Defensa en profundidad (B-10): precios no negativos y el precio
        # cobrado nunca por encima del original (solo se descuenta).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio_original__gte=0),
                name='detalle_precio_original_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(precio_unitario__gte=0),
                name='detalle_precio_unitario_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name='detalle_subtotal_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(precio_unitario__lte=models.F('precio_original')),
                name='detalle_precio_descuento_lte_original'),
        ]

    def __str__(self):
        return f'{self.cantidad}x {self.producto.nombre_completo}'

    @property
    def descuento(self):
        return (self.precio_original - self.precio_unitario) * self.cantidad
