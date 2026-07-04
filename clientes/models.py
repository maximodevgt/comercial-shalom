from django.db import models


class Cliente(models.Model):
    """Cliente registrado. Puede acumular saldo a favor (p. ej. por una
    anulación o la cancelación de un apartado)."""

    nombre = models.CharField('nombre', max_length=150)
    telefono = models.CharField('teléfono', max_length=30, blank=True)
    direccion = models.CharField('dirección', max_length=255, blank=True)
    saldo_favor = models.DecimalField(
        'saldo a favor', max_digits=10, decimal_places=2, default=0)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'
        ordering = ('nombre',)

    def __str__(self):
        return self.nombre
