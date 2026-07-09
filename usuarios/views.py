from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from .forms import DOMINIO_CORREO, UsuarioCrearForm, UsuarioEditarForm
from .models import RegistroActividad, Usuario, registrar_actividad
from .permisos import RolRequeridoMixin, rol_requerido
from .utils import _entero_o_none


class LoginView(auth_views.LoginView):
    """Inicio de sesión con template en español."""

    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Cierre de sesión (requiere POST)."""

    next_page = reverse_lazy('usuarios:login')


class InicioView(LoginRequiredMixin, TemplateView):
    """Dashboard de inicio. Admin/supervisor ven la versión completa con
    gráficas; el cajero ve una versión reducida con sus números del día."""

    template_name = 'inicio.html'

    def get_context_data(self, **kwargs):
        from reportes.consultas import datos_dashboard

        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        usuario = u if (u.es_cajero and not u.es_admin) else None
        ctx.update(datos_dashboard(usuario=usuario))
        return ctx


class SoloAdminMixin(RolRequeridoMixin):
    roles_permitidos = ()  # solo admin


class UsuarioListView(SoloAdminMixin, ListView):
    model = Usuario
    template_name = 'usuarios/lista.html'
    context_object_name = 'usuarios'
    paginate_by = 50
    ordering = ('username',)


class UsuarioCreateView(SoloAdminMixin, CreateView):
    model = Usuario
    form_class = UsuarioCrearForm
    template_name = 'usuarios/usuario_form.html'
    success_url = reverse_lazy('usuarios:lista')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        registrar_actividad(
            self.request.user, RegistroActividad.Tipo.USUARIO,
            f'Creó el usuario «{self.object.username}» ({self.object.get_rol_display()})',
            usuario_creado=self.object.username)
        messages.success(self.request, 'Usuario creado correctamente.')
        return respuesta

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['dominio'] = DOMINIO_CORREO
        ctx['es_creacion'] = True
        return ctx


class UsuarioUpdateView(SoloAdminMixin, UpdateView):
    model = Usuario
    form_class = UsuarioEditarForm
    template_name = 'usuarios/usuario_form.html'
    success_url = reverse_lazy('usuarios:lista')

    def get_queryset(self):
        # Un admin de rol NO puede tocar superusuarios: editar o resetear la
        # contraseña de un superuser sería una escalada de privilegios (A-1).
        qs = super().get_queryset()
        if not self.request.user.is_superuser:
            qs = qs.filter(is_superuser=False)
        return qs

    def get_object(self, queryset=None):
        try:
            return super().get_object(queryset)
        except Http404:
            # Si el 404 fue por el filtro anti-escalada, deja rastro del intento.
            objetivo = Usuario.objects.filter(
                pk=self.kwargs.get('pk'), is_superuser=True).first()
            if objetivo and not self.request.user.is_superuser:
                registrar_actividad(
                    self.request.user, RegistroActividad.Tipo.USUARIO,
                    f'Intento BLOQUEADO de editar al superusuario «{objetivo.username}»',
                    usuario_afectado=objetivo.username)
            raise

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        registrar_actividad(
            self.request.user, RegistroActividad.Tipo.USUARIO,
            f'Editó el usuario «{self.object.username}»',
            usuario_editado=self.object.username)
        messages.success(self.request, 'Usuario actualizado.')
        return respuesta

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['dominio'] = DOMINIO_CORREO
        ctx['es_creacion'] = False
        return ctx


@rol_requerido()  # solo admin
@require_POST
def toggle_activo(request, pk):
    """Activa o desactiva un usuario (en vez de eliminarlo)."""
    usuario = get_object_or_404(Usuario, pk=pk)
    # Un admin de rol NO puede desactivar a un superusuario (A-1): sería
    # apagar la cuenta más privilegiada del sistema. Se registra el intento.
    if usuario.is_superuser and not request.user.is_superuser:
        registrar_actividad(
            request.user, RegistroActividad.Tipo.USUARIO,
            f'Intento BLOQUEADO de desactivar al superusuario «{usuario.username}»',
            usuario_afectado=usuario.username)
        raise Http404('No existe.')
    if usuario.pk == request.user.pk:
        messages.error(request, 'No podés desactivar tu propia cuenta.')
        return redirect('usuarios:lista')
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])
    estado = 'activó' if usuario.is_active else 'desactivó'
    registrar_actividad(
        request.user, RegistroActividad.Tipo.USUARIO,
        f'{estado.capitalize()} al usuario «{usuario.username}»',
        usuario_afectado=usuario.username, activo=usuario.is_active)
    messages.success(request, f'Usuario {estado}.')
    return redirect('usuarios:lista')


class RegistroActividadListView(SoloAdminMixin, ListView):
    model = RegistroActividad
    template_name = 'usuarios/logs.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = RegistroActividad.objects.select_related('usuario')
        tipo = self.request.GET.get('tipo', '').strip()
        # Un valor no numérico se ignora en vez de romper con 500 (M-4).
        usuario = _entero_o_none(self.request.GET.get('usuario'))
        if tipo:
            qs = qs.filter(tipo=tipo)
        if usuario:
            qs = qs.filter(usuario_id=usuario)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tipos'] = RegistroActividad.Tipo.choices
        ctx['usuarios'] = Usuario.objects.all()
        ctx['tipo_sel'] = self.request.GET.get('tipo', '')
        ctx['usuario_sel'] = self.request.GET.get('usuario', '')
        return ctx
