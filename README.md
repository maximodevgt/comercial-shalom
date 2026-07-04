# Comercial Shalom — Sistema web POS

Punto de venta (POS) web para **Comercial Shalom**, desarrollado con **Python + Django**. Gestiona productos e inventario, ventas, apartados (layaway), clientes con saldo a favor, cierres diarios, reportes y una bitácora de actividad, con control de acceso por rol.

## Funcionalidades

- **Autenticación por roles**: administrador, cajero y supervisor. Login por usuario o correo.
- **Productos y categorías**: CRUD, fotos, búsqueda y filtros, estados de stock (agotado / bajo / ok).
- **Clientes**: perfil con historial y saldo a favor.
- **Ventas (POS)**: interfaz de dos columnas (catálogo + ticket), descuentos por línea, pago en efectivo/tarjeta, aplicación de saldo. Los totales se recalculan y validan en el backend; el stock se descuenta de forma atómica con bloqueo de filas.
- **Anulaciones** (admin): restauran stock y restituyen el saldo aplicado.
- **Apartados**: abonos parciales, liquidación (genera la venta) y cancelación (restaura stock y acredita lo abonado como saldo).
- **PDFs**: ticket de venta, comprobante de abono, liquidación, cierre diario y reporte por fecha.
- **Cierre diario y reportes**: totales solo de ventas completadas.
- **Dashboard**: tarjetas del día, stock bajo y gráficas (Chart.js).
- **Gestión de usuarios y bitácora** (admin).

## Stack

- Python 3.14, Django 6.0
- MariaDB 11.8 (driver `mysqlclient`)
- `django-environ` (configuración vía `.env`), Pillow (fotos), xhtml2pdf (PDFs)
- Bootstrap 5 y Chart.js por CDN

## Cómo levantarlo

Requiere Python 3 y una base MariaDB/MySQL con una base de datos `comercial_shalom` (charset `utf8mb4`, collation `utf8mb4_unicode_ci`).

```bash
# 1. Entorno virtual y dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configuración: copiar la plantilla y completar valores reales
cp .env.example .env
#   Editá .env con tu SECRET_KEY y las credenciales de la base (DB_NAME,
#   DB_USER, DB_PASSWORD, DB_HOST, DB_PORT). El .env NO se commitea.

# 3. Migraciones
python manage.py migrate

# 4. Datos de demostración (opcional; imprime usuarios de prueba)
python manage.py seed_demo

# 5. Usuario administrador (si no usás el seed)
python manage.py createsuperuser

# 6. Servidor de desarrollo
python manage.py runserver
```

Luego entrá en <http://127.0.0.1:8000/>.

## Tests

```bash
python manage.py test
```

## Licencia

Ver [LICENSE](LICENSE).
