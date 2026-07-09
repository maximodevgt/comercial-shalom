from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Cliente

Usuario = get_user_model()


class ClientesTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(
            username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.supervisor = Usuario.objects.create_user(
            username='sup', password='x', rol=Usuario.Rol.SUPERVISOR)

    def test_crear_cliente_saldo_inicial_cero(self):
        cliente = Cliente.objects.create(nombre='Juan Pérez', telefono='55512345')
        self.assertEqual(cliente.saldo_favor, Decimal('0'))

    def test_cajero_puede_crear_cliente(self):
        self.client.force_login(self.cajero)
        respuesta = self.client.post(reverse('clientes:crear'), {
            'nombre': 'María López',
            'telefono': '55598765',
            'direccion': 'Zona 1',
        })
        cliente = Cliente.objects.get(nombre='María López')
        self.assertRedirects(respuesta, reverse('clientes:detalle', args=[cliente.pk]))
        self.assertEqual(cliente.saldo_favor, Decimal('0'))

    def test_supervisor_no_puede_crear_cliente(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse('clientes:crear'))
        self.assertEqual(respuesta.status_code, 403)

    def test_solo_admin_elimina(self):
        cliente = Cliente.objects.create(nombre='Borrar')
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse('clientes:eliminar', args=[cliente.pk])).status_code, 403)
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse('clientes:eliminar', args=[cliente.pk]))
        self.assertRedirects(respuesta, reverse('clientes:lista'))
        self.assertFalse(Cliente.objects.filter(pk=cliente.pk).exists())

    def test_busqueda_por_nombre(self):
        Cliente.objects.create(nombre='Ana')
        Cliente.objects.create(nombre='Beto')
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse('clientes:lista'), {'q': 'Ana'})
        self.assertContains(respuesta, 'Ana')
        self.assertNotContains(respuesta, '>Beto<')


class EliminarClienteTest(TestCase):
    """M-5: no se borra un cliente con saldo a favor (dinero que el negocio
    le debe); el borrado exitoso queda en la bitácora."""

    def setUp(self):
        from usuarios.models import RegistroActividad
        self.RegistroActividad = RegistroActividad
        self.admin = Usuario.objects.create_user(
            username='adm_del', password='x', rol=Usuario.Rol.ADMIN)
        self.client.force_login(self.admin)

    def test_no_se_borra_cliente_con_saldo_a_favor(self):
        c = Cliente.objects.create(nombre='Con Saldo', saldo_favor=Decimal('50.00'))
        r = self.client.post(reverse('clientes:eliminar', args=[c.pk]))
        self.assertRedirects(r, reverse('clientes:detalle', args=[c.pk]))
        self.assertTrue(Cliente.objects.filter(pk=c.pk).exists())  # sigue vivo

    def test_borrar_cliente_sin_saldo_deja_bitacora(self):
        c = Cliente.objects.create(nombre='Sin Saldo')
        r = self.client.post(reverse('clientes:eliminar', args=[c.pk]))
        self.assertRedirects(r, reverse('clientes:lista'))
        self.assertFalse(Cliente.objects.filter(pk=c.pk).exists())
        self.assertTrue(self.RegistroActividad.objects.filter(
            tipo=self.RegistroActividad.Tipo.CLIENTE,
            descripcion__icontains='Sin Saldo').exists())
