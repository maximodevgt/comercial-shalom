from django.db import models


class Proveedor(models.Model):
    """Proveedor que surte productos al comercio. El teléfono es el dato
    clave para el negocio (pedidos y reposiciones por llamada/WhatsApp)."""

    nombre = models.CharField('nombre del contacto', max_length=150)
    empresa = models.CharField('empresa', max_length=150)
    telefono = models.CharField('teléfono', max_length=30)
    email = models.EmailField('correo', blank=True)
    direccion = models.CharField('dirección', max_length=255, blank=True)
    notas = models.TextField('notas', blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'proveedor'
        verbose_name_plural = 'proveedores'
        ordering = ('empresa',)

    def __str__(self):
        return f'{self.empresa} — {self.nombre}'
