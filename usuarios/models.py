from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuario del sistema POS con rol para control de permisos.

    Extiende AbstractUser (username, password, nombre, email, etc.) y agrega
    el campo `rol`, que determina qué acciones puede realizar en el sistema.
    """

    class Rol(models.TextChoices):
        ADMIN = 'admin', 'Administrador'
        CAJERO = 'cajero', 'Cajero'
        SUPERVISOR = 'supervisor', 'Supervisor'

    rol = models.CharField(
        'rol',
        max_length=20,
        choices=Rol.choices,
        default=Rol.CAJERO,
        help_text='Determina los permisos del usuario dentro del sistema.',
    )

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def __str__(self):
        nombre = self.get_full_name() or self.username
        return f'{nombre} ({self.get_rol_display()})'

    # Helpers de rol para usar en vistas y templates.
    @property
    def es_admin(self):
        return self.rol == self.Rol.ADMIN

    @property
    def es_cajero(self):
        return self.rol == self.Rol.CAJERO

    @property
    def es_supervisor(self):
        return self.rol == self.Rol.SUPERVISOR
