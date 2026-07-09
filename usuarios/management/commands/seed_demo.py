"""Comando idempotente para poblar datos de demostración.

Uso:  python manage.py seed_demo

Crea categorías, productos (con stock bajo y uno agotado), clientes (uno con
saldo a favor) y usuarios de prueba (cajero y supervisor). Se puede correr
varias veces sin duplicar.

Seguridad (M-2): las contraseñas de los usuarios de demo se GENERAN al azar
en cada corrida y se imprimen una sola vez en la consola (no existen
hardcodeadas en el código ni en el repo). Además, el comando se rehúsa a
correr con DEBUG=False: es solo para entornos de desarrollo."""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management.utils import get_random_secret_key
from django.db import transaction

from clientes.models import Cliente
from productos.models import Categoria, Producto
from usuarios.models import Usuario

CATEGORIAS = ['Zapatos', 'Ropa', 'Accesorios', 'Electrónica']

# (nombre, modelo, color, categoria, precio, stock)
PRODUCTOS = [
    ('Tenis deportivos', 'Runner X', 'Negro', 'Zapatos', '350.00', 12),
    ('Tenis deportivos', 'Runner X', 'Blanco', 'Zapatos', '350.00', 2),   # stock bajo
    ('Sandalias', 'Verano', 'Café', 'Zapatos', '180.00', 0),              # agotado
    ('Playera básica', 'Algodón', 'Azul', 'Ropa', '85.00', 30),
    ('Pantalón de mezclilla', 'Slim', 'Índigo', 'Ropa', '250.00', 8),
    ('Gorra', 'Clásica', 'Rojo', 'Accesorios', '120.00', 1),              # stock bajo
    ('Cinturón de cuero', 'Formal', 'Negro', 'Accesorios', '160.00', 15),
    ('Audífonos', 'BT-500', 'Negro', 'Electrónica', '420.00', 6),
    ('Cargador rápido', 'USB-C 20W', 'Blanco', 'Electrónica', '150.00', 2),  # stock bajo
    ('Reloj digital', 'Sport', 'Gris', 'Electrónica', '600.00', 4),
]

CLIENTES = [
    ('Juan Pérez', '5555-1111', 'Zona 1, Ciudad', Decimal('0.00')),
    ('María López', '5555-2222', 'Zona 10, Ciudad', Decimal('200.00')),  # con saldo
]


class Command(BaseCommand):
    help = 'Crea datos de demostración de forma idempotente.'

    @transaction.atomic
    def handle(self, *args, **options):
        # Doble candado (M-2): datos ficticios y usuarios de prueba no tienen
        # lugar en producción.
        if not settings.DEBUG:
            raise CommandError(
                'seed_demo es solo para entornos de desarrollo (DEBUG=True): '
                'crea usuarios de prueba y datos ficticios.')

        self.stdout.write('Sembrando datos de demostración...')

        # Contraseñas aleatorias por corrida (nunca hardcodeadas).
        pw_cajero = get_random_secret_key()[:12]
        pw_supervisor = get_random_secret_key()[:12]

        categorias = {}
        for nombre in CATEGORIAS:
            cat, _ = Categoria.objects.get_or_create(nombre=nombre)
            categorias[nombre] = cat

        creados_prod = 0
        for nombre, modelo, color, cat, precio, stock in PRODUCTOS:
            _, creado = Producto.objects.get_or_create(
                nombre=nombre, modelo=modelo, color=color,
                defaults={
                    'categoria': categorias[cat],
                    'precio': Decimal(precio),
                    'stock': stock,
                    'activo': True,
                })
            creados_prod += 1 if creado else 0

        for nombre, tel, dir_, saldo in CLIENTES:
            Cliente.objects.get_or_create(
                nombre=nombre,
                defaults={'telefono': tel, 'direccion': dir_, 'saldo_favor': saldo})

        cajero, creado_c = Usuario.objects.get_or_create(
            username='cajero',
            defaults={'first_name': 'Carlos', 'last_name': 'Caja',
                      'email': 'cajero@comercialshalom.com',
                      'rol': Usuario.Rol.CAJERO})
        if creado_c:
            cajero.set_password(pw_cajero)
            cajero.save()

        supervisor, creado_s = Usuario.objects.get_or_create(
            username='supervisor',
            defaults={'first_name': 'Sofía', 'last_name': 'Supervisora',
                      'email': 'supervisor@comercialshalom.com',
                      'rol': Usuario.Rol.SUPERVISOR})
        if creado_s:
            supervisor.set_password(pw_supervisor)
            supervisor.save()

        self.stdout.write(self.style.SUCCESS('¡Datos de demostración listos!'))
        self.stdout.write('')
        self.stdout.write(f'  Categorías: {Categoria.objects.count()}')
        self.stdout.write(f'  Productos:  {Producto.objects.count()} '
                          f'(1 agotado, varios con stock bajo)')
        self.stdout.write(f'  Clientes:   {Cliente.objects.count()} '
                          f'(uno con Q 200 de saldo a favor)')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Usuarios de prueba (guardá estas credenciales: se muestran SOLO acá y una vez):'))
        if creado_c:
            self.stdout.write(f'  cajero      / {pw_cajero}  (rol: cajero)')
        else:
            self.stdout.write('  cajero      → ya existía; su contraseña no se modificó')
        if creado_s:
            self.stdout.write(f'  supervisor  / {pw_supervisor}  (rol: supervisor)')
        else:
            self.stdout.write('  supervisor  → ya existía; su contraseña no se modificó')
