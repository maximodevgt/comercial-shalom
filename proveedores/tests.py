from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Proveedor

Usuario = get_user_model()


class ProveedorTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.prov = Proveedor.objects.create(
            nombre='Juan Pérez', empresa='Distribuidora GT', telefono='5555-1111')

    def test_admin_crea_proveedor(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('proveedores:crear'), {
            'empresa': 'Importadora Sur', 'nombre': 'Ana Ruiz',
            'telefono': '5555-2222', 'email': '', 'direccion': '', 'notas': '',
        })
        self.assertEqual(r.status_code, 302)
        nuevo = Proveedor.objects.get(empresa='Importadora Sur')
        self.assertEqual(str(nuevo), 'Importadora Sur — Ana Ruiz')

    def test_cajero_recibe_403(self):
        self.client.force_login(self.cajero)
        for url in [
            reverse('proveedores:lista'),
            reverse('proveedores:crear'),
            reverse('proveedores:detalle', args=[self.prov.pk]),
            reverse('proveedores:editar', args=[self.prov.pk]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        # También el POST directo de eliminación.
        r = self.client.post(reverse('proveedores:eliminar', args=[self.prov.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Proveedor.objects.filter(pk=self.prov.pk).exists())

    def test_busqueda_filtra(self):
        Proveedor.objects.create(nombre='Otro', empresa='Zapatos SA', telefono='4444-0000')
        self.client.force_login(self.admin)
        r = self.client.get(reverse('proveedores:lista'), {'q': 'Distribuidora'})
        proveedores = list(r.context['proveedores'])
        self.assertEqual(proveedores, [self.prov])
        # Por teléfono también encuentra.
        r2 = self.client.get(reverse('proveedores:lista'), {'q': '4444'})
        self.assertEqual([p.empresa for p in r2.context['proveedores']], ['Zapatos SA'])

    def test_telefono_es_requerido(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('proveedores:crear'), {
            'empresa': 'Sin Tel', 'nombre': 'X', 'telefono': '',
        })
        self.assertEqual(r.status_code, 200)  # re-render con error
        self.assertFalse(Proveedor.objects.filter(empresa='Sin Tel').exists())
