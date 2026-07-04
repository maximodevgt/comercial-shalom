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
    """Panel de inicio tras el login. El contenido se ajusta según el rol."""

    template_name = 'inicio.html'
