import threading
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apartados.models import Apartado
from apartados.servicios import crear_apartado, liquidar_apartado, registrar_abono
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

    def test_anular_venta_normal_cambia_estado_y_restaura_stock(self):
        # (a) Una venta normal se sigue anulando: estado ANULADA y stock +cant.
        venta = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 2, 'precio_unitario': '100.00'}])
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 8)
        self.assertFalse(venta.es_de_liquidacion)  # no proviene de apartado
        anular_venta(self.admin, venta.id, 'devolución')
        self.p.refresh_from_db(); venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertEqual(self.p.stock, 10)  # restaurado (+2)

    def test_no_se_puede_anular_venta_de_liquidacion(self):
        # (b) Escenario real con los servicios: apartado saldado y liquidado.
        apartado = crear_apartado(
            self.cajero, producto_id=self.p.id, precio_total='100.00',
            abono_inicial='60.00')
        registrar_abono(self.cajero, apartado.id, '40.00')  # salda el pendiente
        venta = liquidar_apartado(self.cajero, apartado.id)

        self.p.refresh_from_db()
        stock_antes = self.p.stock  # -1 al crear el apartado; liquidar no toca stock
        self.assertTrue(venta.es_de_liquidacion)

        with self.assertRaises(ErrorAnulacion):
            anular_venta(self.admin, venta.id, 'intento de anulación')

        # Nada cambió: venta completada, stock intacto, apartado liquidado.
        venta.refresh_from_db(); self.p.refresh_from_db()
        apartado.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.COMPLETADA)
        self.assertEqual(self.p.stock, stock_antes)
        self.assertEqual(apartado.estado, Apartado.Estado.LIQUIDADO)


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


class VentaTarjetaTest(TestCase):
    """Con tarjeta, el monto que marca el POS del banco ES el total real de la
    venta; la diferencia contra los precios de lista queda como ajuste."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='adm_tj', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(
            username='caja_tj', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.p235 = Producto.objects.create(
            categoria=self.cat, nombre='P235', precio=Decimal('235.00'), stock=10)
        self.p100 = Producto.objects.create(
            categoria=self.cat, nombre='P100', precio=Decimal('100.00'), stock=10)

    def _venta_tarjeta(self, monto):
        return crear_venta(self.cajero, metodo_pago='tarjeta', monto_tarjeta=monto,
                           lineas=[{'producto_id': self.p235.id, 'cantidad': 1,
                                    'precio_unitario': '235.00'}])

    def test_total_es_lo_que_cobro_el_pos(self):
        # Productos por Q235, el POS cobró Q250 → el total registrado es Q250.
        venta = self._venta_tarjeta('250.00')
        self.assertEqual(venta.total, Decimal('250.00'))
        self.assertEqual(venta.monto_tarjeta, Decimal('250.00'))
        self.assertEqual(venta.subtotal, Decimal('235.00'))
        self.assertEqual(venta.ajuste_tarjeta, Decimal('15.00'))  # recargo

    def test_cierre_suma_lo_cobrado_y_desglosa_por_metodo(self):
        from reportes.consultas import resumen_dia
        self._venta_tarjeta('250.00')
        crear_venta(self.cajero, metodo_pago='efectivo', lineas=[
            {'producto_id': self.p100.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        r = resumen_dia(timezone.localdate())
        self.assertEqual(r['total_vendido'], Decimal('350.00'))  # 250 + 100
        self.assertEqual(r['total_tarjeta'], Decimal('250.00'))
        self.assertEqual(r['total_efectivo'], Decimal('100.00'))

    def test_ajuste_negativo_si_el_pos_cobro_menos(self):
        venta = self._venta_tarjeta('220.00')
        self.assertEqual(venta.total, Decimal('220.00'))
        self.assertEqual(venta.ajuste_tarjeta, Decimal('-15.00'))

    def test_monto_cero_o_negativo_rechazado(self):
        for monto in ('0', '-10.00'):
            with self.assertRaises(ErrorVenta):
                self._venta_tarjeta(monto)
        self.p235.refresh_from_db()
        self.assertEqual(self.p235.stock, 10)  # rollback
        self.assertEqual(Venta.objects.count(), 0)

    def test_monto_desproporcionado_rechazado(self):
        # Más del doble (o menos de la mitad) del total calculado: error de
        # digitación casi seguro. No se registra nada.
        for monto in ('600.00', '100.00'):
            with self.assertRaises(ErrorVenta):
                self._venta_tarjeta(monto)
        self.assertEqual(Venta.objects.count(), 0)

    def test_total_cero_por_saldo_rechaza_cobro_con_tarjeta(self):
        # M-6: el saldo a favor cubre el 100% → cualquier monto de tarjeta
        # inflaría el total registrado. Se rechaza y nada se persiste.
        cliente = Cliente.objects.create(nombre='C', saldo_favor=Decimal('500.00'))
        with self.assertRaises(ErrorVenta) as ctx:
            crear_venta(self.cajero, cliente_id=cliente.id, aplicar_saldo=True,
                        metodo_pago='tarjeta', monto_tarjeta='50.00',
                        lineas=[{'producto_id': self.p235.id, 'cantidad': 1,
                                 'precio_unitario': '235.00'}])
        self.assertIn('no hay nada que cobrar con tarjeta', str(ctx.exception))
        self.p235.refresh_from_db(); cliente.refresh_from_db()
        self.assertEqual(self.p235.stock, 10)                      # rollback stock
        self.assertEqual(cliente.saldo_favor, Decimal('500.00'))   # rollback saldo
        self.assertEqual(Venta.objects.count(), 0)

    def test_sin_monto_asume_el_total_calculado(self):
        venta = crear_venta(self.cajero, metodo_pago='tarjeta', lineas=[
            {'producto_id': self.p235.id, 'cantidad': 1, 'precio_unitario': '235.00'}])
        self.assertEqual(venta.total, Decimal('235.00'))
        self.assertEqual(venta.monto_tarjeta, Decimal('235.00'))
        self.assertEqual(venta.ajuste_tarjeta, Decimal('0.00'))

    def test_venta_efectivo_intacta(self):
        venta = crear_venta(self.cajero, metodo_pago='efectivo', lineas=[
            {'producto_id': self.p235.id, 'cantidad': 1, 'precio_unitario': '235.00'}])
        self.assertEqual(venta.total, Decimal('235.00'))
        self.assertIsNone(venta.monto_tarjeta)
        self.assertEqual(venta.ajuste_tarjeta, Decimal('0.00'))

    def test_anular_venta_tarjeta_restituye_todo(self):
        from reportes.consultas import resumen_dia
        venta = self._venta_tarjeta('250.00')
        self.p235.refresh_from_db()
        self.assertEqual(self.p235.stock, 9)
        anular_venta(self.admin, venta.id, 'devolución')
        venta.refresh_from_db(); self.p235.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertEqual(self.p235.stock, 10)  # stock restaurado
        r = resumen_dia(timezone.localdate())
        self.assertEqual(r['total_vendido'], Decimal('0.00'))  # no suma
        self.assertEqual(r['total_tarjeta'], Decimal('0.00'))


class HistorialFiltroFechaTest(TestCase):
    """El historial muestra SOLO hoy por defecto; ?todas=1 abre el histórico."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='adm', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(
            username='cj', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(
            categoria=self.cat, nombre='P', precio=Decimal('100'), stock=100)

        # Venta de HOY (Q100).
        self.venta_hoy = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 1, 'precio_unitario': '100.00'}])
        # Venta de hace 5 días (Q200): se fuerza `creado` a una fecha pasada.
        self.venta_pasada = crear_venta(self.cajero, lineas=[
            {'producto_id': self.p.id, 'cantidad': 2, 'precio_unitario': '100.00'}])
        self.dia_pasado = timezone.localdate() - timedelta(days=5)
        pasado_mediodia = timezone.make_aware(
            datetime.combine(self.dia_pasado, time(12, 0)))
        Venta.objects.filter(pk=self.venta_pasada.pk).update(creado=pasado_mediodia)

        self.client.force_login(self.admin)

    def test_sin_params_muestra_solo_hoy(self):
        # (a) Sin filtros: aparece solo la venta de hoy y el total es el de hoy.
        r = self.client.get(reverse('ventas:historial'))
        ids = [v.pk for v in r.context['ventas']]
        self.assertIn(self.venta_hoy.pk, ids)
        self.assertNotIn(self.venta_pasada.pk, ids)
        self.assertEqual(r.context['total_vendido'], Decimal('100.00'))
        self.assertEqual(r.context['num_completadas'], 1)

    def test_todas_incluye_dias_anteriores(self):
        # (b) ?todas=1: aparecen las de días anteriores y el total es el histórico.
        r = self.client.get(reverse('ventas:historial'), {'todas': '1'})
        ids = [v.pk for v in r.context['ventas']]
        self.assertIn(self.venta_hoy.pk, ids)
        self.assertIn(self.venta_pasada.pk, ids)
        self.assertEqual(r.context['total_vendido'], Decimal('300.00'))  # 100 + 200
        self.assertEqual(r.context['num_completadas'], 2)

    def test_rango_explicito_respeta_fechas(self):
        # (c) desde/hasta explícito: solo lo que cae en el rango.
        f = self.dia_pasado.strftime('%Y-%m-%d')
        r = self.client.get(reverse('ventas:historial'), {'desde': f, 'hasta': f})
        ids = [v.pk for v in r.context['ventas']]
        self.assertIn(self.venta_pasada.pk, ids)
        self.assertNotIn(self.venta_hoy.pk, ids)
        self.assertEqual(r.context['total_vendido'], Decimal('200.00'))

    def test_filtro_cajero_no_numerico_no_revienta(self):
        # M-4: basura en ?cajero se ignora en vez de romper con 500.
        r = self.client.get(reverse('ventas:historial'), {'cajero': 'abc'})
        self.assertEqual(r.status_code, 200)

    def test_periodo_label_por_caso(self):
        # (d) El texto del período es correcto en cada caso.
        hoy = timezone.localdate()
        d_pasado = hoy - timedelta(days=5)

        r = self.client.get(reverse('ventas:historial'))
        self.assertEqual(r.context['periodo_label'], f'Hoy — {hoy:%d/%m/%Y}')
        self.assertTrue(r.context['es_hoy'])

        r = self.client.get(reverse('ventas:historial'), {'todas': '1'})
        self.assertEqual(r.context['periodo_label'], 'Todas las ventas')
        self.assertFalse(r.context['es_hoy'])

        r = self.client.get(reverse('ventas:historial'), {
            'desde': d_pasado.strftime('%Y-%m-%d'), 'hasta': hoy.strftime('%Y-%m-%d')})
        self.assertEqual(
            r.context['periodo_label'],
            f'Del {d_pasado:%d/%m/%Y} al {hoy:%d/%m/%Y}')

        r = self.client.get(reverse('ventas:historial'), {
            'desde': hoy.strftime('%Y-%m-%d'), 'hasta': hoy.strftime('%Y-%m-%d')})
        self.assertEqual(r.context['periodo_label'], f'Día {hoy:%d/%m/%Y}')
