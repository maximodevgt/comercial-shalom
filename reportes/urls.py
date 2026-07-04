from django.urls import path

from . import views

app_name = 'reportes'

urlpatterns = [
    path('cierre/', views.CierreDiarioView.as_view(), name='cierre'),
    path('cierre/pdf/', views.cierre_pdf, name='cierre_pdf'),
    path('reporte/', views.ReporteFechaView.as_view(), name='reporte'),
    path('reporte/pdf/', views.reporte_pdf, name='reporte_pdf'),
    path('venta/<int:pk>/pdf/', views.ticket_venta_pdf, name='ticket_venta_pdf'),
    path('abono/<int:pk>/pdf/', views.comprobante_abono_pdf, name='comprobante_abono_pdf'),
    path('apartado/<int:pk>/liquidacion/pdf/', views.ticket_liquidacion_pdf, name='ticket_liquidacion_pdf'),
]
