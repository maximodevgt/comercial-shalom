"""Consultas de resumen para cierre diario y reportes.

Regla de oro #7: los totales se calculan con agregados sobre el queryset
completo. TODAS las consultas de dinero filtran estado='completada' para que
los números cuadren exactos con el dashboard."""
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from ventas.models import DetalleVenta, Venta


def resumen_dia(fecha, usuario=None):
    """Resumen de ventas COMPLETADAS de una fecha. Si se pasa `usuario`, se
    filtra a las ventas de ese cajero."""
    ventas = (
        Venta.objects
        .filter(estado=Venta.Estado.COMPLETADA, creado__date=fecha)
        .select_related('cliente', 'usuario')
        .prefetch_related('detalles__producto')
    )
    if usuario is not None:
        ventas = ventas.filter(usuario=usuario)

    total_vendido = ventas.aggregate(
        t=Coalesce(Sum('total'), Decimal('0.00')))['t']
    productos_vendidos = (
        DetalleVenta.objects
        .filter(venta__in=ventas)
        .aggregate(c=Coalesce(Sum('cantidad'), 0))['c']
    )
    return {
        'fecha': fecha,
        'ventas': ventas,
        'total_vendido': total_vendido,
        'num_ventas': ventas.count(),
        'productos_vendidos': productos_vendidos,
    }
