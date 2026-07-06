import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from clientes.models import Cliente
from productos.models import Categoria, Producto

from .models import Venta
from .servicios import ErrorAnulacion, ErrorVenta, anular_venta, crear_venta

Usuario = get_user_model()


class VentaServicioTest(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='General')
        self.a = Producto.objects.create(
            categoria=self.cat, nombre='A', precio=Decimal('100.00'), stock=10)
        self.b = Producto.objects.create(
            categoria=self.cat, nombre='B', precio=Decimal('50.00'), stock=10)

    def test_venta_multiproducto_con_descuento_recalcula_backend(self):
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.a.id, 'cantidad': 2, 'precio_unitario': '90.00'},
            {'producto_id': self.b.id, 'cantidad': 1, 'precio_unitario': '50.00'},
        ])
        self.assertEqual(venta.subtotal, Decimal('230.00'))
        self.assertEqual(venta.descuento_total, Decimal('20.00'))
        self.assertEqual(venta.total, Decimal('230.00'))
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual(self.a.stock, 8)
        self.assertEqual(self.b.stock, 9)

    def test_precio_manipulado_mayor_al_de_bd_es_rechazado(self):
        with self.assertRaises(ErrorVenta):
            crear_venta(self.cajero, lineas=[
                {'producto_id': self.a.id, 'cantidad': 1, 'precio_unitario': '120.00'},
            ])
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)  # rollback
        self.assertEqual(Venta.objects.count(), 0)

    def test_venta_que_supera_stock_es_rechazada(self):
        with self.assertRaises(ErrorVenta):
            crear_venta(self.cajero, lineas=[
                {'producto_id': self.a.id, 'cantidad': 11, 'precio_unitario': '100.00'},
            ])
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        self.assertEqual(Venta.objects.count(), 0)

    def test_lineas_duplicadas_que_exceden_stock_se_rechazan_agrupadas(self):
        # Producto con stock 5: dos líneas de 4 (8 en total) deben fallar con
        # ErrorVenta claro, no con IntegrityError al dejar el stock negativo.
        p = Producto.objects.create(
            categoria=self.cat, nombre='C', precio=Decimal('100.00'), stock=5)
        with self.assertRaises(ErrorVenta) as ctx:
            crear_venta(self.cajero, lineas=[
                {'producto_id': p.id, 'cantidad': 4, 'precio_unitario': '100.00'},
                {'producto_id': p.id, 'cantidad': 4, 'precio_unitario': '90.00'},
            ])
        self.assertIn('Stock insuficiente', str(ctx.exception))
        p.refresh_from_db()
        self.assertEqual(p.stock, 5)  # nada descontado
        self.assertEqual(Venta.objects.count(), 0)

    def test_lineas_duplicadas_que_caben_descuentan_bien(self):
        # Dos líneas del mismo producto (precios distintos) que SÍ caben:
        # se mantienen separadas en los detalles y el stock queda correcto.
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.a.id, 'cantidad': 3, 'precio_unitario': '100.00'},
            {'producto_id': self.a.id, 'cantidad': 2, 'precio_unitario': '80.00'},
        ])
        self.assertEqual(venta.detalles.count(), 2)
        self.assertEqual(venta.subtotal, Decimal('460.00'))   # 300 + 160
        self.assertEqual(venta.descuento_total, Decimal('40.00'))
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 5)  # 10 − 3 − 2

    def test_saldo_debitado_y_capeado(self):
        # Saldo mayor que la compra: se aplica solo lo necesario.
        cliente = Cliente.objects.create(nombre='C', saldo_favor=Decimal('500.00'))
        venta = crear_venta(
            self.cajero, cliente_id=cliente.id, aplicar_saldo=True,
            lineas=[{'producto_id': self.a.id, 'cantidad': 2, 'precio_unitario': '100.00'}])
        self.assertEqual(venta.subtotal, Decimal('200.00'))
        self.assertEqual(venta.saldo_aplicado, Decimal('200.00'))
        self.assertEqual(venta.total, Decimal('0.00'))
        cliente.refresh_from_db()
        self.assertEqual(cliente.saldo_favor, Decimal('300.00'))

    def test_saldo_menor_que_compra_se_aplica_completo(self):
        cliente = Cliente.objects.create(nombre='C', saldo_favor=Decimal('50.00'))
        venta = crear_venta(
            self.cajero, cliente_id=cliente.id, aplicar_saldo=True,
            lineas=[{'producto_id': self.a.id, 'cantidad': 2, 'precio_unitario': '100.00'}])
        self.assertEqual(venta.saldo_aplicado, Decimal('50.00'))
        self.assertEqual(venta.total, Decimal('150.00'))
        cliente.refresh_from_db()
        self.assertEqual(cliente.saldo_favor, Decimal('0.00'))


class VentaVistasTest(TestCase):
    def setUp(self):
        self.cajero1 = Usuario.objects.create_user(username='c1', password='x', rol=Usuario.Rol.CAJERO)
        self.cajero2 = Usuario.objects.create_user(username='c2', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(categoria=self.cat, nombre='P', precio=Decimal('10'), stock=5)
        self.venta1 = crear_venta(self.cajero1, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '10.00'}])

    def test_cajero_no_ve_venta_de_otro(self):
        self.client.force_login(self.cajero2)
        r = self.client.get(reverse('ventas:detalle', args=[self.venta1.pk]))
        self.assertEqual(r.status_code, 403)

    def test_cajero_solo_ve_sus_ventas_en_historial(self):
        crear_venta(self.cajero2, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '10.00'}])
        self.client.force_login(self.cajero1)
        r = self.client.get(reverse('ventas:historial'))
        ventas = r.context['ventas']
        self.assertTrue(all(v.usuario_id == self.cajero1.id for v in ventas))

    def test_supervisor_no_puede_abrir_pos(self):
        sup = Usuario.objects.create_user(username='s', password='x', rol=Usuario.Rol.SUPERVISOR)
        self.client.force_login(sup)
        self.assertEqual(self.client.get(reverse('ventas:pos')).status_code, 403)


class AnulacionTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(categoria=self.cat, nombre='P', precio=Decimal('100'), stock=10)

    def test_anular_con_saldo_restaura_stock_y_restituye_saldo(self):
        cliente = Cliente.objects.create(nombre='C', saldo_favor=Decimal('300.00'))
        venta = crear_venta(self.cajero, cliente_id=cliente.id, aplicar_saldo=True,
                            lineas=[{'producto_id': self.p.id, 'cantidad': 2, 'precio_unitario': '100.00'}])
        self.p.refresh_from_db(); cliente.refresh_from_db()
        self.assertEqual(self.p.stock, 8)
        self.assertEqual(cliente.saldo_favor, Decimal('100.00'))  # 300 - 200

        anular_venta(self.admin, venta.id, 'Cliente se arrepintió')
        self.p.refresh_from_db(); cliente.refresh_from_db(); venta.refresh_from_db()
        self.assertEqual(self.p.stock, 10)  # stock restaurado
        self.assertEqual(cliente.saldo_favor, Decimal('300.00'))  # saldo restituido
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertEqual(venta.motivo_anulacion, 'Cliente se arrepintió')

    def test_anular_sin_cliente_no_falla(self):
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        anular_venta(self.admin, venta.id, 'Error de digitación')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)

    def test_motivo_obligatorio(self):
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        with self.assertRaises(ErrorAnulacion):
            anular_venta(self.admin, venta.id, '   ')

    def test_no_se_puede_anular_dos_veces(self):
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        anular_venta(self.admin, venta.id, 'motivo')
        with self.assertRaises(ErrorAnulacion):
            anular_venta(self.admin, venta.id, 'otra vez')

    def test_anular_no_siendo_admin_devuelve_403(self):
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        self.client.force_login(self.cajero)
        r = self.client.post(reverse('ventas:anular', args=[venta.id]), {'motivo': 'x'})
        self.assertEqual(r.status_code, 403)
        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.COMPLETADA)

    def test_venta_anulada_no_cuenta_en_totales(self):
        v1 = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        v2 = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        anular_venta(self.admin, v2.id, 'anulada')
        self.client.force_login(self.admin)
        r = self.client.get(reverse('ventas:historial'))
        self.assertEqual(r.context['total_vendido'], Decimal('100.00'))
        self.assertEqual(r.context['num_completadas'], 1)
        self.assertEqual(r.context['num_anuladas'], 1)


class VentaConcurrenciaTest(TransactionTestCase):
    """Verifica el select_for_update con dos ventas concurrentes del último ítem."""

    def test_dos_ventas_concurrentes_solo_una_pasa(self):
        cajero = Usuario.objects.create_user(username='cc', password='x', rol=Usuario.Rol.CAJERO)
        cat = Categoria.objects.create(nombre='G')
        producto = Producto.objects.create(categoria=cat, nombre='Ultimo', precio=Decimal('10'), stock=1)

        resultados = []

        def vender():
            try:
                crear_venta(cajero, lineas=[
                    {'producto_id': producto.id, 'cantidad': 1, 'precio_unitario': '10.00'}])
                resultados.append('ok')
            except ErrorVenta:
                resultados.append('fail')
            finally:
                connection.close()

        t1 = threading.Thread(target=vender)
        t2 = threading.Thread(target=vender)
        t1.start(); t2.start(); t1.join(); t2.join()

        self.assertEqual(resultados.count('ok'), 1)
        self.assertEqual(resultados.count('fail'), 1)
        producto.refresh_from_db()
        self.assertEqual(producto.stock, 0)
        self.assertEqual(Venta.objects.count(), 1)
