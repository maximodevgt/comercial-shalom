from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

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

    def test_cajero_es_rechazado(self):
        with self.assertRaises(PermissionDenied):
            self._pedir(self.cajero)

    def test_superusuario_cuenta_como_admin(self):
        # Aunque su rol sea 'cajero', un superusuario debe pasar como admin.
        superusuario = Usuario.objects.create_superuser(
            username='root', password='x', rol=Usuario.Rol.CAJERO)
        self.assertTrue(superusuario.es_admin)
        self.assertEqual(self._pedir(superusuario).status_code, 200)
