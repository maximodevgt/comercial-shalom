from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    name = 'usuarios'

    def ready(self):
        # Registra los signals (log de inicio de sesión).
        from . import signals  # noqa: F401
