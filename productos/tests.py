import io
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from usuarios.models import RegistroActividad

from .models import Categoria, Producto

Usuario = get_user_model()


def imagen_png(nombre='foto.png'):
    """Genera un PNG en memoria para probar el ImageField."""
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(buffer, format='PNG')
    buffer.seek(0)
    return SimpleUploadedFile(nombre, buffer.read(), content_type='image/png')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductosTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin', password='x', rol=Usuario.Rol.ADMIN)
        self.cajero = Usuario.objects.create_user(
            username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.categoria = Categoria.objects.create(nombre='Zapatos')

    def test_crear_categoria(self):
        self.assertEqual(Categoria.objects.count(), 1)
        self.assertEqual(str(self.categoria), 'Zapatos')

    def test_crear_producto_con_foto(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse('productos:crear'), {
            'categoria': self.categoria.id,
            'nombre': 'Tenis',
            'modelo': 'Runner',
            'color': 'Negro',
            'precio': '199.99',
            'stock': '5',
            'activo': 'on',
            'foto': imagen_png(),
        })
        self.assertRedirects(respuesta, reverse('productos:lista'))
        p = Producto.objects.get(nombre='Tenis')
        self.assertTrue(p.foto)
        self.assertEqual(p.nombre_completo, 'Tenis - Runner - Negro')
        self.assertEqual(p.estado_stock, 'ok')

    def test_cajero_no_puede_crear(self):
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse('productos:crear'))
        self.assertEqual(respuesta.status_code, 403)

    def test_cajero_ve_listado(self):
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse('productos:lista'))
        self.assertEqual(respuesta.status_code, 200)

    def test_cambio_de_precio_genera_log(self):
        producto = Producto.objects.create(
            categoria=self.categoria, nombre='Bota', precio=Decimal('100.00'), stock=3)
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse('productos:editar', args=[producto.pk]), {
            'categoria': self.categoria.id,
            'nombre': 'Bota',
            'modelo': '',
            'color': '',
            'precio': '150.00',
            'stock': '3',
            'activo': 'on',
        })
        self.assertRedirects(respuesta, reverse('productos:lista'))
        log = RegistroActividad.objects.filter(tipo=RegistroActividad.Tipo.PRODUCTO).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.datos['precio']['anterior'], '100.00')
        self.assertEqual(log.datos['precio']['nuevo'], '150.00')

    def test_estados_de_stock(self):
        p0 = Producto.objects.create(categoria=self.categoria, nombre='A', precio=Decimal('1'), stock=0)
        p1 = Producto.objects.create(categoria=self.categoria, nombre='B', precio=Decimal('1'), stock=2)
        p2 = Producto.objects.create(categoria=self.categoria, nombre='C', precio=Decimal('1'), stock=10)
        self.assertEqual(p0.estado_stock, 'agotado')
        self.assertEqual(p1.estado_stock, 'bajo')
        self.assertEqual(p2.estado_stock, 'ok')

    def test_eliminar_categoria_con_productos_es_protegido(self):
        Producto.objects.create(categoria=self.categoria, nombre='X', precio=Decimal('1'), stock=1)
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse('productos:categoria_eliminar', args=[self.categoria.pk]))
        self.assertRedirects(respuesta, reverse('productos:categorias'))
        self.assertTrue(Categoria.objects.filter(pk=self.categoria.pk).exists())
