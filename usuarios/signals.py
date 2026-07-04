from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import RegistroActividad, registrar_actividad


@receiver(user_logged_in)
def registrar_inicio_sesion(sender, request, user, **kwargs):
    """Deja constancia del inicio de sesión en la bitácora (tipo Sesión)."""
    registrar_actividad(
        user, RegistroActividad.Tipo.SESION,
        f'Inició sesión: {user.username}')
