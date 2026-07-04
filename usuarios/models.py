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
        # Un superusuario de Django cuenta siempre como admin, sin importar
        # el valor del campo `rol` (evita inconsistencias con createsuperuser).
        return self.rol == self.Rol.ADMIN or self.is_superuser

    @property
    def es_cajero(self):
        return self.rol == self.Rol.CAJERO

    @property
    def es_supervisor(self):
        return self.rol == self.Rol.SUPERVISOR


class RegistroActividad(models.Model):
    """Bitácora de acciones sensibles del sistema (regla de oro #8).

    Registra anulaciones, cambios de precio/stock, eliminaciones, descuentos,
    inicios de sesión, etc. El campo `datos` guarda contexto estructurado
    (valores anterior→nuevo, montos, motivo).
    """

    class Tipo(models.TextChoices):
        ANULACION = 'anulacion', 'Anulación'
        PRODUCTO = 'producto', 'Producto'
        DESCUENTO = 'descuento', 'Descuento'
        SALDO = 'saldo', 'Saldo'
        APARTADO = 'apartado', 'Apartado'
        SESION = 'sesion', 'Sesión'
        USUARIO = 'usuario', 'Usuario'

    usuario = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actividades',
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.CharField(max_length=255)
    datos = models.JSONField(default=dict, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'registro de actividad'
        verbose_name_plural = 'registros de actividad'
        ordering = ('-creado',)
        indexes = [
            models.Index(fields=['tipo']),
            models.Index(fields=['-creado']),
        ]

    def __str__(self):
        return f'[{self.get_tipo_display()}] {self.descripcion}'


def registrar_actividad(usuario, tipo, descripcion, **datos):
    """Helper para crear un RegistroActividad de forma concisa.

    Los kwargs extra se guardan en el campo JSON `datos`. Los Decimal se
    serializan a str para que JSONField no falle.
    """
    from decimal import Decimal

    datos_limpios = {
        k: (str(v) if isinstance(v, Decimal) else v) for k, v in datos.items()
    }
    return RegistroActividad.objects.create(
        usuario=usuario,
        tipo=tipo,
        descripcion=descripcion,
        datos=datos_limpios,
    )
