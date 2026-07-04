from django.db import models

from .validators import validar_foto_producto


class Categoria(models.Model):
    """Categoría de productos (p. ej. Zapatos, Ropa, Accesorios)."""

    nombre = models.CharField('nombre', max_length=100, unique=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'
        ordering = ('nombre',)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    """Producto del inventario del POS."""

    STOCK_BAJO_UMBRAL = 2

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name='productos',
        verbose_name='categoría',
    )
    nombre = models.CharField('nombre', max_length=120)
    modelo = models.CharField('modelo', max_length=120, blank=True)
    color = models.CharField('color', max_length=60, blank=True)
    precio = models.DecimalField('precio', max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField('stock', default=0)
    activo = models.BooleanField('activo', default=True)
    foto = models.ImageField(
        'foto',
        upload_to='productos/',
        blank=True,
        null=True,
        validators=[validar_foto_producto],
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'producto'
        verbose_name_plural = 'productos'
        ordering = ('nombre', 'modelo', 'color')

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self):
        """'nombre - modelo - color', omitiendo las partes vacías."""
        partes = [self.nombre]
        if self.modelo:
            partes.append(self.modelo)
        if self.color:
            partes.append(self.color)
        return ' - '.join(partes)

    @property
    def estado_stock(self):
        if self.stock == 0:
            return 'agotado'
        if self.stock <= self.STOCK_BAJO_UMBRAL:
            return 'bajo'
        return 'ok'

    @property
    def disponible(self):
        """Se puede vender: activo y con stock."""
        return self.activo and self.stock > 0
