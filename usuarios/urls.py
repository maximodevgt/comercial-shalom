from django.urls import path

from . import views

app_name = 'usuarios'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    # Gestión de usuarios (solo admin)
    path('usuarios/', views.UsuarioListView.as_view(), name='lista'),
    path('usuarios/nuevo/', views.UsuarioCreateView.as_view(), name='crear'),
    path('usuarios/<int:pk>/editar/', views.UsuarioUpdateView.as_view(), name='editar'),
    path('usuarios/<int:pk>/toggle/', views.toggle_activo, name='toggle_activo'),
    # Bitácora de actividad (solo admin)
    path('logs/', views.RegistroActividadListView.as_view(), name='logs'),
]
