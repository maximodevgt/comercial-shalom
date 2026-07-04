from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

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

    def test_abono_no_supera_pendiente(self):
        apartado = crear_apartado(
            self.cajero, producto_id=self.producto.id, precio_total='500.00',
            abono_inicial='400.00')
        # Intenta abonar 300 cuando solo quedan 100: se capea a 100.
        registrar_abono(self.cajero, apartado.id, '300.00')
        apartado.refresh_from_db()
        self.assertEqual(apartado.total_abonado, Decimal('500.00'))
        self.assertEqual(apartado.pendiente, Decimal('0.00'))

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
