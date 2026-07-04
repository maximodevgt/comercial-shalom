"""Configuración de URLs del proyecto comercial-shalom."""
from django.contrib import admin
from django.urls import include, path

from usuarios.views import InicioView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/', include('usuarios.urls')),
    path('', InicioView.as_view(), name='inicio'),
]
