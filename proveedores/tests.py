from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import Categoria, Producto

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


class ProductoProveedorTest(TestCase):
    """La FK Producto→Proveedor: asignación, visualización y PROTECT."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cat = Categoria.objects.create(nombre='G')
        self.prov = Proveedor.objects.create(
            nombre='Juan Pérez', empresa='Distribuidora GT', telefono='5555-1111')

    def test_producto_con_proveedor_se_guarda_y_se_muestra(self):
        p = Producto.objects.create(
            categoria=self.cat, proveedor=self.prov, nombre='Lámpara',
            precio=Decimal('75.00'), stock=4)
        self.assertEqual(p.proveedor.empresa, 'Distribuidora GT')
        self.assertIn(p, self.prov.productos.all())
        self.client.force_login(self.admin)
        # La lista de productos muestra la empresa (columna solo admin).
        r = self.client.get(reverse('productos:lista'))
        self.assertContains(r, 'Distribuidora GT')
        # El detalle del proveedor lista el producto que surte.
        r2 = self.client.get(reverse('proveedores:detalle', args=[self.prov.pk]))
        self.assertContains(r2, 'Lámpara')

    def test_eliminar_proveedor_con_productos_es_rechazado(self):
        Producto.objects.create(
            categoria=self.cat, proveedor=self.prov, nombre='Lámpara',
            precio=Decimal('75.00'), stock=4)
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse('proveedores:eliminar', args=[self.prov.pk]), follow=True)
        self.assertTrue(Proveedor.objects.filter(pk=self.prov.pk).exists())  # sigue vivo
        mensajes = [str(m) for m in r.context['messages']]
        self.assertTrue(any('productos asociados' in m for m in mensajes))

    def test_form_de_producto_acepta_proveedor_opcional(self):
        from productos.forms import ProductoForm
        form = ProductoForm(data={
            'categoria': self.cat.pk, 'proveedor': '', 'nombre': 'Sin prov',
            'modelo': '', 'color': '', 'precio': '10.00', 'stock': 1, 'activo': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        producto = form.save()
        self.assertIsNone(producto.proveedor)
