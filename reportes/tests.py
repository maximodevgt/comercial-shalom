from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from productos.models import Categoria, Producto
from ventas.servicios import anular_venta, crear_venta

from .consultas import datos_dashboard, resumen_dia

Usuario = get_user_model()


class ReportesTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(categoria=self.cat, nombre='P', precio=Decimal('100'), stock=50)
        # Dos completadas y una anulada, todas de hoy.
        self.v1 = crear_venta(self.cajero, lineas=[{'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        self.v2 = crear_venta(self.cajero, lineas=[{'producto_id': self.p.id, 'cantidad': 2, 'precio_unitario': '100.00'}])
        self.v3 = crear_venta(self.cajero, lineas=[{'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        anular_venta(self.admin, self.v3.id, 'anulada')

    def test_cierre_excluye_anuladas(self):
        resumen = resumen_dia(timezone.localdate())
        # v1 (100) + v2 (200) = 300; v3 anulada NO cuenta.
        self.assertEqual(resumen['total_vendido'], Decimal('300.00'))
        self.assertEqual(resumen['num_ventas'], 2)
        self.assertEqual(resumen['productos_vendidos'], 3)  # 1 + 2

    def test_reporte_fecha_muestra_solo_completadas(self):
        self.client.force_login(self.admin)
        hoy = timezone.localdate().strftime('%Y-%m-%d')
        r = self.client.get(reverse('reportes:reporte'), {'fecha': hoy})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_vendido'], Decimal('300.00'))
        self.assertEqual(r.context['num_ventas'], 2)

    def test_pdf_de_venta_se_genera(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('reportes:ticket_venta_pdf', args=[self.v1.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_pdf_cierre_se_genera(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('reportes:cierre_pdf'))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_reporte_solo_admin_supervisor(self):
        self.client.force_login(self.cajero)
        r = self.client.get(reverse('reportes:reporte'))
        self.assertEqual(r.status_code, 403)

    def test_cierre_cajero_ve_solo_lo_suyo(self):
        otro = Usuario.objects.create_user(username='c2', password='x', rol=Usuario.Rol.CAJERO)
        crear_venta(otro, lineas=[{'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        self.client.force_login(self.cajero)
        r = self.client.get(reverse('reportes:cierre'))
        # El cajero solo suma sus 2 completadas (300), no la del otro cajero.
        self.assertEqual(r.context['total_vendido'], Decimal('300.00'))
        self.assertTrue(r.context['solo_propias'])


class DashboardTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(categoria=self.cat, nombre='P', precio=Decimal('100'), stock=50)

    def test_anular_baja_total_y_cuadra_con_cierre(self):
        crear_venta(self.cajero, lineas=[{'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        v2 = crear_venta(self.cajero, lineas=[{'producto_id': self.p.id, 'cantidad': 2, 'precio_unitario': '100.00'}])

        dash = datos_dashboard()
        cierre = resumen_dia(timezone.localdate())
        self.assertEqual(dash['total_hoy'], Decimal('300.00'))
        self.assertEqual(dash['total_hoy'], cierre['total_vendido'])  # cuadran

        anular_venta(self.admin, v2.id, 'anulada')

        dash2 = datos_dashboard()
        cierre2 = resumen_dia(timezone.localdate())
        self.assertEqual(dash2['total_hoy'], Decimal('100.00'))  # bajó
        self.assertEqual(dash2['total_hoy'], cierre2['total_vendido'])  # sigue cuadrando

    def test_dashboard_renderiza_para_admin(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('inicio'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context['reducido'])

    def test_dashboard_reducido_para_cajero(self):
        self.client.force_login(self.cajero)
        r = self.client.get(reverse('inicio'))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['reducido'])
