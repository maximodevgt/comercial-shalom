from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import RegistroActividad
from .permisos import rol_requerido

Usuario = get_user_model()


class LoginSmokeTest(TestCase):
    """Smoke test del flujo de autenticación."""

    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username='cajero1',
            password='clave-segura-123',
            rol=Usuario.Rol.CAJERO,
        )

    def test_login_correcto_redirige_al_inicio(self):
        respuesta = self.client.post(
            reverse('usuarios:login'),
            {'username': 'cajero1', 'password': 'clave-segura-123'},
        )
        self.assertRedirects(respuesta, reverse('inicio'))

    def test_login_incorrecto_no_autentica(self):
        respuesta = self.client.post(
            reverse('usuarios:login'),
            {'username': 'cajero1', 'password': 'mal'},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_inicio_requiere_autenticacion(self):
        respuesta = self.client.get(reverse('inicio'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('usuarios:login'), respuesta.url)

    def test_inicio_autenticado_responde_ok(self):
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse('inicio'))
        self.assertEqual(respuesta.status_code, 200)


class PermisosPorRolTest(TestCase):
    """Verifica el decorador de restricción por rol."""

    def setUp(self):
        self.factory = RequestFactory()
        self.cajero = Usuario.objects.create_user(
            username='caja', password='x', rol=Usuario.Rol.CAJERO)
        self.supervisor = Usuario.objects.create_user(
            username='super', password='x', rol=Usuario.Rol.SUPERVISOR)
        self.admin = Usuario.objects.create_user(
            username='jefe', password='x', rol=Usuario.Rol.ADMIN)

        @rol_requerido(Usuario.Rol.SUPERVISOR)
        def vista_solo_supervisor(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        self.vista = vista_solo_supervisor

    def _pedir(self, usuario):
        request = self.factory.get('/panel/')
        request.user = usuario
        return self.vista(request)

    def test_supervisor_accede(self):
        self.assertEqual(self._pedir(self.supervisor).status_code, 200)

    def test_admin_siempre_accede(self):
        self.assertEqual(self._pedir(self.admin).status_code, 200)

    def test_cajero_es_rechazado_permisos(self):
        with self.assertRaises(PermissionDenied):
            self._pedir(self.cajero)

    def test_superusuario_cuenta_como_admin(self):
        # Aunque su rol sea 'cajero', un superusuario debe pasar como admin.
        superusuario = Usuario.objects.create_superuser(
            username='root', password='x', rol=Usuario.Rol.CAJERO)
        self.assertTrue(superusuario.es_admin)
        self.assertEqual(self._pedir(superusuario).status_code, 200)


class GestionUsuariosTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin', password='x', rol=Usuario.Rol.ADMIN)

    def test_crear_usuario_cajero_puede_loguearse(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('usuarios:crear'), {
            'username': 'nuevocajero',
            'first_name': 'Nuevo',
            'last_name': 'Cajero',
            'correo_usuario': 'nuevo',
            'rol': Usuario.Rol.CAJERO,
            'password': 'Cajero2026x',
        })
        self.assertRedirects(r, reverse('usuarios:lista'))
        nuevo = Usuario.objects.get(username='nuevocajero')
        self.assertEqual(nuevo.email, 'nuevo@comercialshalom.com')
        self.assertEqual(nuevo.rol, Usuario.Rol.CAJERO)
        # Puede iniciar sesión con su username.
        self.client.logout()
        self.assertTrue(self.client.login(username='nuevocajero', password='Cajero2026x'))

    def test_login_con_correo_funciona(self):
        Usuario.objects.create_user(
            username='concorreo', email='concorreo@comercialshalom.com',
            password='Correo2026x', rol=Usuario.Rol.CAJERO)
        # Autentica usando el correo como identificador (backend custom).
        ok = self.client.login(username='concorreo@comercialshalom.com', password='Correo2026x')
        self.assertTrue(ok)

    def test_desactivar_usuario(self):
        cajero = Usuario.objects.create_user(username='c', password='x', rol=Usuario.Rol.CAJERO)
        self.client.force_login(self.admin)
        r = self.client.post(reverse('usuarios:toggle_activo', args=[cajero.pk]))
        self.assertRedirects(r, reverse('usuarios:lista'))
        cajero.refresh_from_db()
        self.assertFalse(cajero.is_active)

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('usuarios:toggle_activo', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_log_de_anulacion_aparece_con_badge(self):
        from productos.models import Categoria, Producto
        from ventas.servicios import anular_venta, crear_venta
        cajero = Usuario.objects.create_user(username='caja', password='x', rol=Usuario.Rol.CAJERO)
        cat = Categoria.objects.create(nombre='G')
        p = Producto.objects.create(categoria=cat, nombre='P', precio=Decimal('10'), stock=5)
        venta = crear_venta(cajero, lineas=[{'producto_id': p.id, 'cantidad': 1, 'precio_unitario': '10.00'}])
        anular_venta(self.admin, venta.id, 'motivo de prueba')
        self.client.force_login(self.admin)
        r = self.client.get(reverse('usuarios:logs'))
        self.assertContains(r, 'Anulación')
        self.assertTrue(RegistroActividad.objects.filter(tipo='anulacion').exists())

    def test_logs_solo_admin(self):
        cajero = Usuario.objects.create_user(username='c', password='x', rol=Usuario.Rol.CAJERO)
        self.client.force_login(cajero)
        self.assertEqual(self.client.get(reverse('usuarios:logs')).status_code, 403)


class ProteccionSuperusuarioTest(TestCase):
    """A-1: un admin de rol NO puede editar, resetear la contraseña ni
    desactivar a un superusuario (escalada de privilegios); un superuser sí."""

    def setUp(self):
        self.admin_rol = Usuario.objects.create_user(
            username='admin_rol', password='x', rol=Usuario.Rol.ADMIN)
        self.superuser = Usuario.objects.create_superuser(
            username='root', email='root@comercialshalom.com',
            password='super-secreta-123')

    def test_admin_de_rol_no_puede_abrir_edicion_de_superusuario(self):
        self.client.force_login(self.admin_rol)
        r = self.client.get(reverse('usuarios:editar', args=[self.superuser.pk]))
        self.assertEqual(r.status_code, 404)

    def test_admin_de_rol_no_puede_resetear_password_de_superusuario(self):
        self.client.force_login(self.admin_rol)
        r = self.client.post(
            reverse('usuarios:editar', args=[self.superuser.pk]),
            {'first_name': 'X', 'last_name': 'Y', 'rol': Usuario.Rol.ADMIN,
             'password': 'NuevaClave123'})
        self.assertEqual(r.status_code, 404)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.check_password('super-secreta-123'))
        # El intento bloqueado queda en la bitácora.
        self.assertTrue(RegistroActividad.objects.filter(
            usuario=self.admin_rol, tipo=RegistroActividad.Tipo.USUARIO,
            descripcion__icontains='BLOQUEADO').exists())

    def test_admin_de_rol_no_puede_desactivar_superusuario(self):
        self.client.force_login(self.admin_rol)
        r = self.client.post(reverse('usuarios:toggle_activo', args=[self.superuser.pk]))
        self.assertEqual(r.status_code, 404)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)
        self.assertTrue(RegistroActividad.objects.filter(
            descripcion__icontains='desactivar al superusuario').exists())

    def test_superusuario_si_puede_editar_a_otro_superusuario(self):
        otro = Usuario.objects.create_superuser(
            username='root2', email='root2@comercialshalom.com', password='x')
        self.client.force_login(self.superuser)
        r = self.client.get(reverse('usuarios:editar', args=[otro.pk]))
        self.assertEqual(r.status_code, 200)


class LogsFiltroBasuraTest(TestCase):
    """M-4: un filtro no numérico en la bitácora se ignora en vez de dar 500."""

    def test_usuario_no_numerico_no_revienta(self):
        admin = Usuario.objects.create_user(
            username='adm_filtro', password='x', rol=Usuario.Rol.ADMIN)
        self.client.force_login(admin)
        r = self.client.get(reverse('usuarios:logs'), {'usuario': 'abc'})
        self.assertEqual(r.status_code, 200)
