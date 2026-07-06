# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Respondé SIEMPRE en español latinoamericano. Todos los mensajes, explicaciones, comentarios de código, mensajes de commit y documentación deben estar en español. El código (nombres de variables, funciones, modelos) también en español, siguiendo la convención del dominio (productos, ventas, categorias, usuarios, cierres).

## Project state

Sistema POS **completo y funcional** (fases 1–10 implementadas). Python 3.14, Django 6.0, PostgreSQL 15 en `127.0.0.1:5432` (base `comercial_shalom`). Frontend con Bootstrap 5, Font Awesome 6 y Chart.js (todo por CDN). Identidad visual definida con variables CSS en `templates/base.html` (`:root`, color primario azul profundo). Íconos solo Font Awesome (sin emojis). Suite de tests verde.

### Apps y modelos

- **`usuarios`** — `Usuario(AbstractUser + rol)` (roles `admin`/`cajero`/`supervisor`), `RegistroActividad` (bitácora). `AUTH_USER_MODEL = 'usuarios.Usuario'`. Permisos en `usuarios/permisos.py` (`rol_requerido`, `RolRequeridoMixin`; `is_superuser` cuenta como admin). Backend de login por username o correo (`usuarios/backends.py`). Signal que loguea inicios de sesión.
- **`productos`** — `Categoria`, `Producto` (precio Decimal, stock, foto `ImageField` validada, properties `nombre_completo`/`estado_stock`). Validador de foto en `productos/validators.py`.
- **`clientes`** — `Cliente` (con `saldo_favor` Decimal; el saldo solo lo mueven ventas/anulaciones/apartados).
- **`ventas`** — `Venta`, `DetalleVenta`. Lógica en `ventas/servicios.py`: `crear_venta()` y `anular_venta()`, todo atómico con `select_for_update()` y recálculo de totales en el backend.
- **`apartados`** — `Apartado`, `Abono`. Lógica en `apartados/servicios.py`: crear/abonar/liquidar/cancelar (atómico, con restitución de saldo y restauración de stock).
- **`reportes`** — sin modelos. `consultas.py` (`resumen_dia`, `datos_dashboard`), `pdf.py` (xhtml2pdf), vistas de cierre diario, reporte por fecha y todos los PDFs.

### Layout relevante

- `config/` — proyecto Django. `templates/` — templates a nivel proyecto (incluye `reportes/pdf/` para los PDFs).
- `.venv/` (ignorado), `.env` / `.env.example` (configuración y secretos, ver más abajo).
- `media/` — fotos de producto subidas (servidas en DEBUG).

### Datos de prueba

`python manage.py seed_demo` — comando idempotente que crea categorías, productos (con stock bajo y uno agotado), clientes (uno con saldo) y usuarios `cajero`/`supervisor`. Las contraseñas se imprimen en el output del comando (no están documentadas en el repo).

### Nota sobre el modelo de usuario custom

Exige aplicar las migraciones desde una base limpia. Si alguna vez hay que volver a cambiar `AUTH_USER_MODEL`, recrear la base (`DROP DATABASE` + `CREATE DATABASE comercial_shalom`).

## Reglas de oro del proyecto

Reglas no negociables para TODO el código (con dónde se cumplen hoy):

1. **Dinero = `DecimalField(max_digits=10, decimal_places=2)`, nunca `float`.** ✅ Todos los modelos con importes (`Producto.precio`, `Cliente.saldo_favor`, `Venta.*`, `DetalleVenta.*`, `Apartado.*`, `Abono.monto`).
2. **Stock/saldo dentro de `transaction.atomic()` con `select_for_update()`** sobre las filas afectadas (producto, cliente). ✅ `ventas/servicios.py`, `apartados/servicios.py`.
3. **Totales recalculados en el backend**, validando contra la base (precio_unitario ≤ precio BD, cantidad ≤ stock, saldo ≤ min(saldo, subtotal)). Nunca se confía en el frontend. ✅ `ventas/servicios.crear_venta()`.
4. **Texto de usuario escapado en JS con `esc()`**; nunca `|safe` sobre input de usuario. ✅ `templates/ventas/pos.html` y demás JS que inserta en el DOM.
5. **Secretos solo en `.env`** (ver sección de configuración). ✅
6. **Vistas protegidas por rol** con `usuarios/permisos.py`: cajero solo lo suyo, supervisor cierre/reportes, admin todo; `is_superuser` = admin. ✅
7. **Historiales paginados de 50** y totales con agregados sobre el queryset filtrado completo (no la página). ✅ ventas, apartados, usuarios, logs, reportes.
8. **`RegistroActividad` en acciones sensibles**: anulaciones, cambios de precio/stock, eliminaciones, descuentos, saldo, apartados, sesión, usuarios. ✅ `usuarios.registrar_actividad()`.
9. **Templates en español, Bootstrap 5 (CDN)**, consistentes con `base.html`. ✅
10. **Fotos de producto**: `ImageField` (Pillow), validación de tipo (jpg/jpeg/png/webp, no svg) y tamaño ≤ 5MB; `MEDIA_ROOT`/`MEDIA_URL` servidos en DEBUG. ✅ `productos/validators.py`, `config/settings.py`, `config/urls.py`.

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
python manage.py seed_demo               # poblar datos de demostración (idempotente)
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

- Motor: **PostgreSQL 15**. Backend Django: `django.db.backends.postgresql`, driver `psycopg2-binary`.
- Base: `comercial_shalom` en `127.0.0.1:5432`.
- Credenciales (usuario, password, host, puerto) van en `.env`, no en el repo.
