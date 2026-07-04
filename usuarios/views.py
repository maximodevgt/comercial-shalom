from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView


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
