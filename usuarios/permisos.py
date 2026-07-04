"""Control de acceso por rol para el POS.

Provee un decorador (`rol_requerido`) para vistas basadas en funciones y un
mixin (`RolRequeridoMixin`) para vistas basadas en clases. En ambos casos:

- Si el usuario no está autenticado -> redirige al login.
- Si está autenticado pero su rol no está permitido -> 403 (PermissionDenied).

El rol de administrador siempre tiene acceso, salvo que se indique lo contrario.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _tiene_acceso(usuario, roles_permitidos, permitir_admin):
    """Decide si `usuario` puede acceder según su rol.

    El admin (rol='admin' o superusuario de Django, vía `es_admin`) siempre
    pasa cuando `permitir_admin` es True.
    """
    if permitir_admin and usuario.es_admin:
        return True
    return usuario.rol in roles_permitidos


def rol_requerido(*roles, permitir_admin=True):
    """Restringe una vista de función a los roles indicados.

    Uso:
        @rol_requerido(Usuario.Rol.CAJERO)
        def registrar_venta(request): ...
    """

    roles_permitidos = set(roles)

    def decorador(vista):
        @wraps(vista)
        @login_required
        def _envoltura(request, *args, **kwargs):
            if not _tiene_acceso(request.user, roles_permitidos, permitir_admin):
                raise PermissionDenied(
                    'No tenés permiso para acceder a esta sección.'
                )
            return vista(request, *args, **kwargs)

        return _envoltura

    return decorador


class RolRequeridoMixin:
    """Mixin para vistas basadas en clases que restringe por rol.

    Definí `roles_permitidos` en la clase:

        class PanelSupervisor(RolRequeridoMixin, TemplateView):
            roles_permitidos = [Usuario.Rol.SUPERVISOR]
    """

    roles_permitidos = ()
    permitir_admin = True

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())

        if not _tiene_acceso(
            request.user, set(self.roles_permitidos), self.permitir_admin
        ):
            raise PermissionDenied(
                'No tenés permiso para acceder a esta sección.'
            )
        return super().dispatch(request, *args, **kwargs)
