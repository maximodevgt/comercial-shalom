"""Migración de datos: en ventas con tarjeta, el monto que marcó el POS del
banco es lo que el cliente pagó de verdad. Las ventas históricas donde
total != monto_tarjeta se actualizan para que los cierres y reportes cuadren
con lo realmente cobrado (misma regla que aplica crear_venta desde ahora)."""
from django.db import migrations
from django.db.models import F


def cuadrar_total_tarjeta(apps, schema_editor):
    Venta = apps.get_model('ventas', 'Venta')
    (Venta.objects
     .filter(metodo_pago='tarjeta', monto_tarjeta__isnull=False)
     .exclude(total=F('monto_tarjeta'))
     .update(total=F('monto_tarjeta')))


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0001_initial'),
    ]

    operations = [
        # Sin reversa real: el total anterior no se guarda en otro campo.
        migrations.RunPython(cuadrar_total_tarjeta, migrations.RunPython.noop),
    ]
