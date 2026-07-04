from django.urls import path

from . import views

app_name = 'apartados'

urlpatterns = [
    path('', views.ApartadoListView.as_view(), name='lista'),
    path('nuevo/', views.crear_apartado_view, name='crear'),
    path('<int:pk>/', views.ApartadoDetailView.as_view(), name='detalle'),
    path('<int:pk>/abonar/', views.abonar_view, name='abonar'),
    path('<int:pk>/liquidar/', views.liquidar_view, name='liquidar'),
    path('<int:pk>/cancelar/', views.cancelar_view, name='cancelar'),
]
