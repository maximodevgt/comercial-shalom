from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Permite iniciar sesión con el username o con el correo electrónico.

    Mantiene todas las validaciones de ModelBackend (contraseña, is_active).
    El match exacto de username tiene PRIORIDAD sobre el correo: si el
    username de una cuenta coincidiera con el email de otra, gana el
    username (B-3/B-1: sin ambigüedad).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        Usuario = get_user_model()
        if username is None:
            username = kwargs.get(Usuario.USERNAME_FIELD)
        if username is None or password is None:
            return None
        # Case-insensitive; first() cubre datos inconsistentes (duplicados).
        usuario = (
            Usuario.objects.filter(username__iexact=username).order_by('id').first()
            or Usuario.objects.filter(email__iexact=username).order_by('id').first()
        )
        if usuario is None:
            # Ejecuta el hasher igual para mitigar timing attacks.
            Usuario().set_password(password)
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
