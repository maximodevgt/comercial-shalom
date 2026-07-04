# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Respondé SIEMPRE en español latinoamericano. Todos los mensajes, explicaciones, comentarios de código, mensajes de commit y documentación deben estar en español. El código (nombres de variables, funciones, modelos) también en español, siguiendo la convención del dominio (productos, ventas, categorias, usuarios, cierres).

## Project state

El scaffold de Django ya está creado. Layout actual:

- `config/` — paquete del proyecto Django (`settings.py`, `urls.py`, `wsgi.py`, `asgi.py`).
- `manage.py` — punto de entrada de Django (en la raíz del repo).
- `requirements.txt` — dependencias pineadas (Django 6.0, `mysqlclient`, `django-environ`).
- `templates/` — templates a nivel proyecto (`base.html`, `inicio.html`, `usuarios/`).
- `.venv/` — entorno virtual (ignorado por git).
- `.env` / `.env.example` — configuración y secretos (ver sección más abajo).

Apps de dominio creadas: `usuarios`, `productos`, `ventas`, `clientes`, `reportes` (registradas en `INSTALLED_APPS`). Por ahora solo `usuarios` tiene modelos; las demás son andamiaje vacío.

**Sprint 1 — autenticación con roles (implementado):**

- Modelo de usuario personalizado `usuarios.Usuario` (`AbstractUser` + campo `rol`). `AUTH_USER_MODEL = 'usuarios.Usuario'`.
- Roles: `admin`, `cajero`, `supervisor` (ver `Usuario.Rol`). Helpers `es_admin` / `es_cajero` / `es_supervisor`.
- Login/logout con `LoginView`/`LogoutView` y templates en español (`templates/usuarios/login.html`). Rutas bajo `cuentas/` (namespace `usuarios`).
- Control de acceso por rol en `usuarios/permisos.py`: decorador `rol_requerido(*roles)` para vistas de función y `RolRequeridoMixin` para CBV. El rol `admin` siempre tiene acceso salvo `permitir_admin=False`.
- **Importante:** el modelo de usuario custom exige que las migraciones se apliquen desde una base limpia. Si alguna vez hay que volver a cambiar `AUTH_USER_MODEL`, se recrea la base (`DROP DATABASE` + `CREATE DATABASE ... utf8mb4`).

Python de referencia: 3.14. Base de datos: MariaDB 11.8 en `127.0.0.1:3306`, base `comercial_shalom`.

## Reglas de oro del proyecto

Reglas no negociables para todo el código que se agregue:

1. **Dinero = `DecimalField`, nunca `FloatField`.** Todos los importes (precios, totales, subtotales, montos de cierre) se modelan con `models.DecimalField(max_digits=..., decimal_places=2)` y se operan con `decimal.Decimal`. Prohibido `float` para dinero — introduce errores de redondeo.
2. **Transacciones de venta atómicas con bloqueo de filas.** Toda operación que registre una venta (crear la venta, descontar inventario, generar líneas, actualizar el cierre diario) va dentro de `transaction.atomic()`, y las filas de stock/producto que se modifican se leen con `select_for_update()` para evitar condiciones de carrera y sobreventa. Ejemplo:

   ```python
   from django.db import transaction

   with transaction.atomic():
       producto = Producto.objects.select_for_update().get(pk=producto_id)
       # validar stock, descontar, crear líneas, actualizar cierre...
   ```
3. **Secretos fuera del código** (ya cubierto en la sección de configuración): nada de credenciales en `settings.py`; todo vía `.env`.

## Intended scope (from README.md)

A web-based POS ("Sistema web POS") built with **Python + Django** for:

- Products (`productos`), categories (`categorías`), and inventory (`inventario`)
- Sales (`ventas`)
- Users (`usuarios`)
- Daily closings (`cierres diarios`)
- Administrative reports (`reportes`)

The codebase and UI are in **Spanish** — follow that convention for model names, field names, routes, and comments.

## Comandos del proyecto

Primero configurar el entorno (una sola vez):

```bash
python3 -m venv .venv                    # crear el entorno virtual
source .venv/bin/activate                # activar el venv (necesario en cada sesión)
pip install -r requirements.txt          # instalar dependencias
cp .env.example .env                     # crear tu .env local y completar los valores
```

Comandos habituales de desarrollo (con el venv activado):

```bash
python manage.py runserver               # levantar el servidor de desarrollo
python manage.py migrate                 # aplicar migraciones a la base
python manage.py makemigrations          # generar migraciones tras cambiar modelos
python manage.py createsuperuser         # crear usuario admin
python manage.py startapp <app>          # crear una nueva app de dominio

python manage.py test                    # correr todos los tests
python manage.py test <app>.<TestCase>.<test_method>  # correr un test puntual
```

> Si no querés activar el venv, podés invocar los binarios directo: `./.venv/bin/python manage.py <comando>`.

## Architecture guidance

The domains above map naturally to separate Django apps (e.g. `productos`, `inventario`, `ventas`, `usuarios`, `reportes`). Keep POS transaction logic (a sale that decrements inventory, records line items, and rolls up into a daily closing) as the core flow — this is the part that spans multiple apps and warrants the most care around atomicity and consistency.

## Configuración y secretos (convención del proyecto)

**Ningún secreto va hardcodeado en `settings.py`** — ni el password de la base, ni el `SECRET_KEY` de Django, ni credenciales de terceros. Toda configuración sensible se maneja con un archivo `.env` fuera del control de versiones.

- Usar `django-environ` (preferido) o `python-dotenv` para leer las variables desde `.env`.
- El archivo `.env` **debe estar excluido en `.gitignore`** y nunca commitearse.
- Mantener un `.env.example` versionado como plantilla, con las claves esperadas pero **sin valores reales** (usar placeholders).
- `settings.py` lee los valores con `env(...)`, p. ej. `DATABASES` toma `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` desde el entorno.

### Base de datos

- Motor: **MariaDB** (drop-in compatible con MySQL; en Fedora 44 el repo oficial ya no incluye `community-mysql`). Backend Django: `django.db.backends.mysql`, driver `mysqlclient`.
- Base: `comercial_shalom` — charset `utf8mb4`, collation `utf8mb4_unicode_ci`.
- Usuario administrador: `root` (auth `mysql_native_password`). El password va en `.env`, no en el repo.
- Dependencias de sistema para compilar `mysqlclient` en Fedora: `mariadb-connector-c-devel`, `gcc`, `make`, `redhat-rpm-config`, `pkgconf-pkg-config`.
