from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    """Permite iniciar sesión con el username o con el correo electrónico.

    Mantiene todas las validaciones de ModelBackend (contraseña, is_active).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        Usuario = get_user_model()
        if username is None:
            username = kwargs.get(Usuario.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            # Case-insensitive por username o email. first() evita error si
            # (por datos inconsistentes) hubiera más de una coincidencia.
            usuario = (
                Usuario.objects.filter(Q(username__iexact=username) | Q(email__iexact=username))
                .order_by('id')
                .first()
            )
        except Usuario.DoesNotExist:
            return None
        if usuario is None:
            # Ejecuta el hasher igual para mitigar timing attacks.
            Usuario().set_password(password)
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
