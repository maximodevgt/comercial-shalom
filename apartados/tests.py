from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from productos.models import Categoria, Producto
from ventas.models import Venta

from .models import Abono, Apartado
from .servicios import (
    ErrorApartado, cancelar_apartado, crear_apartado, liquidar_apartado,
    registrar_abono,
)

Usuario = get_user_model()


class ApartadoTest(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Reloj', precio=Decimal('500.00'), stock=3)
        self.cliente = Cliente.objects.create(nombre='Cliente', saldo_favor=Decimal('0'))

    def test_crear_apartado_descuenta_stock(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            cliente_id=self.cliente.id, abono_inicial='100.00')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 2)  # descontó 1
        self.assertEqual(apartado.total_abonado, Decimal('100.00'))
        self.assertEqual(apartado.pendiente, Decimal('400.00'))

    def test_apartado_con_descuento_persistido(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='450.00')
        self.assertEqual(apartado.precio_original, Decimal('500.00'))
        self.assertEqual(apartado.precio_total, Decimal('450.00'))
        self.assertEqual(apartado.descuento, Decimal('50.00'))

    def test_precio_no_puede_superar_lista(self):
        with self.assertRaises(ErrorApartado):
            crear_apartado(self.cajero, producto_id=self.producto.id, precio_total='600.00')

    def test_abono_efectivo_mayor_al_pendiente_es_rechazado(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            abono_inicial='400.00')
        # Abonar 300 cuando solo quedan 100 se RECHAZA (antes se capeaba en
        # silencio y el excedente en efectivo quedaba sin rastro).
        with self.assertRaises(ErrorApartado) as ctx:
            registrar_abono(self.cajero, apartado.id, '300.00')
        msg = str(ctx.exception)
        self.assertIn('300.00', msg)  # monto tecleado
        self.assertIn('100.00', msg)  # pendiente real
        apartado.refresh_from_db()
        self.assertEqual(apartado.total_abonado, Decimal('400.00'))  # sin cambios
        self.assertEqual(apartado.pendiente, Decimal('100.00'))

    def test_abono_exacto_al_pendiente_liquida_sin_error(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            abono_inicial='400.00')
        registrar_abono(self.cajero, apartado.id, '100.00')
        apartado.refresh_from_db()
        self.assertEqual(apartado.pendiente, Decimal('0.00'))
        venta = liquidar_apartado(self.cajero, apartado.id)
        self.assertEqual(venta.total, Decimal('500.00'))

    def test_abono_inicial_mayor_al_precio_es_rechazado(self):
        # El abono inicial de crear_apartado pasa por la misma regla.
        with self.assertRaises(ErrorApartado):
            crear_apartado(
                self.cajero, producto_id=self.producto.id, precio_total='500.00',
                abono_inicial='600.00')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)  # rollback completo

    def test_abono_saldo_mayor_al_pendiente_se_capea(self):
        self.cliente.saldo_favor = Decimal('600.00')
        self.cliente.save()
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            cliente_id=self.cliente.id, abono_inicial='450.00')
        # Con método saldo se capea a min(saldo, pendiente) = 50, como antes.
        registrar_abono(self.cajero, apartado.id, '600.00', Abono.Metodo.SALDO)
        apartado.refresh_from_db(); self.cliente.refresh_from_db()
        self.assertEqual(apartado.pendiente, Decimal('0.00'))
        self.assertEqual(self.cliente.saldo_favor, Decimal('550.00'))  # 600 − 50

    def test_abono_con_saldo_debita_cliente(self):
        self.cliente.saldo_favor = Decimal('200.00')
        self.cliente.save()
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            cliente_id=self.cliente.id)
        registrar_abono(self.cajero, apartado.id, '300.00', Abono.Metodo.SALDO)
        self.cliente.refresh_from_db(); apartado.refresh_from_db()
        # Capeado a min(monto, pendiente, saldo) = min(300, 500, 200) = 200
        self.assertEqual(self.cliente.saldo_favor, Decimal('0.00'))
        self.assertEqual(apartado.total_abonado, Decimal('200.00'))

    def test_liquidacion_crea_venta_correcta(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='450.00',
            cliente_id=self.cliente.id, abono_inicial='450.00')
        stock_antes = Producto.objects.get(pk=self.producto.id).stock
        venta = liquidar_apartado(self.cajero, apartado.id)
        apartado.refresh_from_db()
        self.assertEqual(apartado.estado, Apartado.Estado.LIQUIDADO)
        self.assertEqual(apartado.venta_id, venta.id)
        self.assertEqual(venta.total, Decimal('450.00'))
        self.assertEqual(venta.descuento_total, Decimal('50.00'))
        # La liquidación NO vuelve a tocar el stock (ya se descontó al crear).
        self.assertEqual(Producto.objects.get(pk=self.producto.id).stock, stock_antes)
        detalle = venta.detalles.get()
        self.assertEqual(detalle.cantidad, 1)
        self.assertEqual(detalle.precio_unitario, Decimal('450.00'))

    def test_no_se_puede_liquidar_con_pendiente(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            abono_inicial='100.00')
        with self.assertRaises(ErrorApartado):
            liquidar_apartado(self.cajero, apartado.id)

    def test_doble_liquidacion_bloqueada(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            abono_inicial='500.00')
        liquidar_apartado(self.cajero, apartado.id)
        with self.assertRaises(ErrorApartado):
            liquidar_apartado(self.cajero, apartado.id)
        self.assertEqual(Venta.objects.count(), 1)

    def test_cancelacion_restaura_stock_y_acredita_saldo(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            cliente_id=self.cliente.id, abono_inicial='150.00')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 2)
        cancelar_apartado(self.cajero, apartado.id)
        self.producto.refresh_from_db(); self.cliente.refresh_from_db(); apartado.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)  # stock restaurado
        self.assertEqual(self.cliente.saldo_favor, Decimal('150.00'))  # abonado acreditado
        self.assertEqual(apartado.estado, Apartado.Estado.CANCELADO)

    def test_cancelacion_sin_cliente_a_cliente_nuevo(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            nombre_cliente_libre='Walk-in', abono_inicial='80.00')
        cancelar_apartado(self.cajero, apartado.id, destino='cliente_nuevo',
                          nuevo_cliente={'nombre': 'Nuevo', 'telefono': '123'})
        nuevo = Cliente.objects.get(nombre='Nuevo')
        self.assertEqual(nuevo.saldo_favor, Decimal('80.00'))


class CancelarSoloAdminTest(TestCase):
    """La cancelación redirige dinero abonado: solo admin (vector de fraude)."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.cat = Categoria.objects.create(nombre='G')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Reloj', precio=Decimal('500.00'), stock=3)
        self.cliente = Cliente.objects.create(nombre='Cliente', saldo_favor=Decimal('0'))
        # Apartado del propio cajero, con Q 150 abonados.
        self.apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            cliente_id=self.cliente.id, abono_inicial='150.00')

    def test_cajero_recibe_403_al_cancelar(self):
        self.client.force_login(self.cajero)
        r = self.client.post(
            reverse('apartados:cancelar', args=[self.apartado.pk]),
            {'destino': 'saldo_cliente'})
        self.assertEqual(r.status_code, 403)
        self.apartado.refresh_from_db()
        self.assertEqual(self.apartado.estado, Apartado.Estado.ACTIVO)  # no pasó nada

    def test_admin_cancela_y_acredita_saldo(self):
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse('apartados:cancelar', args=[self.apartado.pk]),
            {'destino': 'saldo_cliente'})
        self.assertEqual(r.status_code, 302)
        self.apartado.refresh_from_db(); self.cliente.refresh_from_db(); self.producto.refresh_from_db()
        self.assertEqual(self.apartado.estado, Apartado.Estado.CANCELADO)
        self.assertEqual(self.cliente.saldo_favor, Decimal('150.00'))  # abonado acreditado
        self.assertEqual(self.producto.stock, 3)  # stock restaurado


class MetodoAbonoInvalidoTest(TestCase):
    """M-3: un método de pago fuera de los choices se rechaza (antes se
    persistía y desaparecía del desglose por método del cierre)."""

    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username='caja_metodo', password='x', rol=Usuario.Rol.CAJERO)
        cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(
            categoria=cat, nombre='P', precio=Decimal('100'), stock=5)

    def test_abono_con_metodo_basura_es_rechazado(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.p.id, precio_total='100.00')
        with self.assertRaises(ErrorApartado):
            registrar_abono(self.cajero, apartado.id, '50.00', metodo='xyz')
        self.assertEqual(Abono.objects.count(), 0)

    def test_abono_inicial_con_metodo_basura_revierte_todo(self):
        with self.assertRaises(ErrorApartado):
            crear_apartado(self.cajero, producto_id=self.p.id,
                           precio_total='100.00', abono_inicial='30.00',
                           metodo_abono='xyz')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 5)  # rollback: stock intacto
        self.assertEqual(Apartado.objects.count(), 0)
        self.assertEqual(Abono.objects.count(), 0)


class ProductoInactivoApartadoTest(TestCase):
    """B-2: un POST directo no puede apartar un producto inactivo (espejo de
    la validación de crear_venta; la vista solo ofrece activos)."""

    def test_apartar_producto_inactivo_es_rechazado(self):
        cajero = Usuario.objects.create_user(
            username='caja_inactivo', password='x', rol=Usuario.Rol.CAJERO)
        cat = Categoria.objects.create(nombre='G')
        p = Producto.objects.create(
            categoria=cat, nombre='Descontinuado', precio=Decimal('100'),
            stock=5, activo=False)
        with self.assertRaises(ErrorApartado):
            crear_apartado(cajero, producto_id=p.id, precio_total='100.00')
        p.refresh_from_db()
        self.assertEqual(p.stock, 5)  # nada descontado
        self.assertEqual(Apartado.objects.count(), 0)


class CancelarApartadoDestinosTest(TestCase):
    """Cobertura de los TRES destinos de cancelar_apartado para apartados SIN
    cliente registrado (el caso con cliente ya está cubierto aparte)."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='adm_dest', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(
            username='caja_dest', password='x', rol=Usuario.Rol.CAJERO)
        cat = Categoria.objects.create(nombre='G')
        self.p = Producto.objects.create(
            categoria=cat, nombre='P', precio=Decimal('100'), stock=5)

    def _apartado_sin_cliente(self):
        # Apartado anónimo con Q40 abonados; el stock baja a 4 al crearlo.
        return crear_apartado(
            self.cajero, producto_id=self.p.id, precio_total='100.00',
            nombre_cliente_libre='Anónimo', abono_inicial='40.00')

    def test_destino_cliente_existente_acredita_saldo(self):
        ap = self._apartado_sin_cliente()
        cli = Cliente.objects.create(nombre='Receptor', saldo_favor=Decimal('10.00'))
        cancelar_apartado(self.admin, ap.id,
                          destino='cliente_existente', cliente_destino_id=cli.id)
        ap.refresh_from_db(); cli.refresh_from_db(); self.p.refresh_from_db()
        self.assertEqual(ap.estado, Apartado.Estado.CANCELADO)
        self.assertEqual(cli.saldo_favor, Decimal('50.00'))  # 10 + 40 abonados
        self.assertEqual(self.p.stock, 5)                    # stock restaurado

    def test_destino_cliente_nuevo_crea_cliente_con_saldo(self):
        ap = self._apartado_sin_cliente()
        cancelar_apartado(self.admin, ap.id, destino='cliente_nuevo',
                          nuevo_cliente={'nombre': 'Creado Al Cancelar',
                                         'telefono': '5555-0000',
                                         'direccion': 'Zona 1'})
        ap.refresh_from_db(); self.p.refresh_from_db()
        nuevo = Cliente.objects.get(nombre='Creado Al Cancelar')
        self.assertEqual(nuevo.saldo_favor, Decimal('40.00'))  # lo abonado
        self.assertEqual(ap.estado, Apartado.Estado.CANCELADO)
        self.assertEqual(self.p.stock, 5)

    def test_destino_perdida_restaura_stock_sin_crear_saldo(self):
        from usuarios.models import RegistroActividad
        ap = self._apartado_sin_cliente()
        clientes_antes = Cliente.objects.count()
        cancelar_apartado(self.admin, ap.id, destino='perdida')
        ap.refresh_from_db(); self.p.refresh_from_db()
        self.assertEqual(ap.estado, Apartado.Estado.CANCELADO)
        self.assertEqual(self.p.stock, 5)                        # restaurado
        self.assertEqual(Cliente.objects.count(), clientes_antes)  # sin saldo nuevo
        # El destino queda documentado en la bitácora.
        log = RegistroActividad.objects.get(
            descripcion=f'Canceló el apartado #{ap.pk}')
        self.assertEqual(log.datos.get('destino'), 'perdida')
        self.assertEqual(log.datos.get('abonado'), '40.00')
