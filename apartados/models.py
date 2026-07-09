from decimal import Decimal

from django.conf import settings
from django.db import models


class Apartado(models.Model):
    """Apartado (layaway): el cliente separa un producto y lo paga en abonos.
    Al crearse descuenta 1 unidad de stock; al liquidarse genera una Venta."""

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        LIQUIDADO = 'liquidado', 'Liquidado'
        CANCELADO = 'cancelado', 'Cancelado'

    cliente = models.ForeignKey(
        'clientes.Cliente', on_delete=models.PROTECT,
        null=True, blank=True, related_name='apartados')
    nombre_cliente_libre = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    direccion = models.CharField(max_length=255, blank=True)

    producto = models.ForeignKey('productos.Producto', on_delete=models.PROTECT)
    precio_original = models.DecimalField(max_digits=10, decimal_places=2)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='apartados')
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ACTIVO)
    venta = models.ForeignKey(
        'ventas.Venta', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='apartado_origen')

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'apartado'
        verbose_name_plural = 'apartados'
        ordering = ('-creado',)
        indexes = [
            models.Index(fields=['estado']),
            models.Index(fields=['-creado']),
        ]
        # Defensa en profundidad (B-10): precios no negativos y el precio
        # apartado nunca por encima del de lista (solo se descuenta).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio_original__gte=0),
                name='apartado_precio_original_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(precio_total__gte=0),
                name='apartado_precio_total_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(precio_total__lte=models.F('precio_original')),
                name='apartado_precio_total_lte_original'),
        ]

    def __str__(self):
        return f'Apartado #{self.pk}'

    @property
    def nombre_cliente(self):
        if self.cliente:
            return self.cliente.nombre
        return self.nombre_cliente_libre or 'Sin nombre'

    @property
    def total_abonado(self):
        # Si el queryset trae la anotación `_total_abonado` (lista de apartados),
        # se usa directo para evitar el N+1; en el detalle y demás vistas cae al
        # aggregate normal.
        if hasattr(self, '_total_abonado'):
            total = self._total_abonado or Decimal('0.00')
        else:
            total = self.abonos.aggregate(s=models.Sum('monto'))['s'] or Decimal('0.00')
        return total.quantize(Decimal('0.01'))

    @property
    def pendiente(self):
        # Delega en total_abonado, así hereda la optimización de la anotación.
        return (self.precio_total - self.total_abonado).quantize(Decimal('0.01'))

    @property
    def descuento(self):
        return (self.precio_original - self.precio_total).quantize(Decimal('0.01'))


class Abono(models.Model):
    """Pago parcial de un apartado."""

    class Metodo(models.TextChoices):
        EFECTIVO = 'efectivo', 'Efectivo'
        TARJETA = 'tarjeta', 'Tarjeta'
        SALDO = 'saldo', 'Saldo a favor'

    apartado = models.ForeignKey(Apartado, on_delete=models.CASCADE, related_name='abonos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=10, choices=Metodo.choices, default=Metodo.EFECTIVO)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='abonos')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'abono'
        verbose_name_plural = 'abonos'
        ordering = ('creado',)
        # Defensa en profundidad (B-10): un abono nunca es negativo.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto__gte=0),
                name='abono_monto_no_negativo'),
        ]

    def __str__(self):
        return f'Abono Q {self.monto} ({self.get_metodo_display()})'
