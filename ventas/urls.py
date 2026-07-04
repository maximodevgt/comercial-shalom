from django.urls import path

from . import views

app_name = 'ventas'

urlpatterns = [
    path('nueva/', views.PosView.as_view(), name='pos'),
    path('registrar/', views.registrar_venta, name='registrar'),
    path('', views.HistorialVentasView.as_view(), name='historial'),
    path('<int:pk>/', views.VentaDetailView.as_view(), name='detalle'),
    path('<int:pk>/anular/', views.anular_venta_view, name='anular'),
]
