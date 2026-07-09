"""Consultas de resumen para cierre diario y reportes.

Regla de oro #7: los totales se calculan con agregados sobre el queryset
completo. TODAS las consultas de dinero filtran estado='completada' para que
los números cuadren exactos con el dashboard."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apartados.models import Abono
from productos.models import Producto
from ventas.models import DetalleVenta, Venta


def _abonos_del_dia(fecha, usuario=None):
    """Abonos de apartados recibidos en `fecha` (por `creado__date`), para el
    cierre. Son dinero que entra a caja pero que NO es una venta: se muestran
    aparte y NO suman a total_vendido.

    Scoping por cajero: se filtra por `apartado__usuario` (el dueño del
    apartado), que es como el resto del sistema define "lo propio" del cajero
    (ver apartados.views._puede_ver), no por quién registró el abono.

    Devuelve (total, por_metodo, cantidad). `por_metodo` recorre
    Abono.Metodo.choices para un orden fijo (efectivo, tarjeta, saldo) e
    incluye solo los métodos con abonos ese día.
    """
    abonos = Abono.objects.filter(creado__date=fecha)
    if usuario is not None:
        abonos = abonos.filter(apartado__usuario=usuario)

    total = abonos.aggregate(t=Coalesce(Sum('monto'), Decimal('0.00')))['t']
    cantidad = abonos.count()
    # Un solo agregado agrupado por método (sin queries por fila).
    por_metodo_raw = {
        fila['metodo']: fila['t']
        for fila in abonos.values('metodo').annotate(t=Coalesce(Sum('monto'), Decimal('0.00')))
    }
    por_metodo = [
        {'metodo_display': etiqueta, 'total': por_metodo_raw[valor]}
        for valor, etiqueta in Abono.Metodo.choices
        if valor in por_metodo_raw
    ]
    return total, por_metodo, cantidad


def resumen_dia(fecha, usuario=None):
    """Resumen de ventas de una fecha. Si se pasa `usuario`, se filtra a las
    ventas de ese cajero.

    Los agregados de DINERO (total_vendido, num_ventas, productos_vendidos)
    se calculan SOLO sobre ventas completadas. Las anuladas se incluyen
    aparte —y en el listado combinado `ventas_dia`— únicamente para control:
    no suman a ningún total.
    """
    ventas = (
        Venta.objects
        .filter(estado=Venta.Estado.COMPLETADA, creado__date=fecha)
        .select_related('cliente', 'usuario')
        .prefetch_related('detalles__producto')
    )
    anuladas = (
        Venta.objects
        .filter(estado=Venta.Estado.ANULADA, creado__date=fecha)
        .select_related('cliente', 'usuario')
        .prefetch_related('detalles__producto')
    )
    if usuario is not None:
        ventas = ventas.filter(usuario=usuario)
        anuladas = anuladas.filter(usuario=usuario)

    total_vendido = ventas.aggregate(
        t=Coalesce(Sum('total'), Decimal('0.00')))['t']
    # Desglose por método de pago (solo completadas): útil para cuadrar el
    # efectivo de caja y lo cobrado contra el POS del banco.
    desglose = ventas.aggregate(
        efectivo=Coalesce(
            Sum('total', filter=Q(metodo_pago=Venta.MetodoPago.EFECTIVO)),
            Decimal('0.00')),
        tarjeta=Coalesce(
            Sum('total', filter=Q(metodo_pago=Venta.MetodoPago.TARJETA)),
            Decimal('0.00')),
    )
    productos_vendidos = (
        DetalleVenta.objects
        .filter(venta__in=ventas)
        .aggregate(c=Coalesce(Sum('cantidad'), 0))['c']
    )
    # Listado combinado (más reciente primero) para las tablas del cierre y
    # el reporte; el estado de cada fila se distingue en el template.
    ventas_dia = sorted(
        [*ventas, *anuladas], key=lambda v: v.creado, reverse=True)

    # Abonos del día (dinero de caja que NO es venta): informativo, aparte.
    total_abonos, abonos_por_metodo, num_abonos = _abonos_del_dia(fecha, usuario)

    return {
        'fecha': fecha,
        'ventas': ventas,
        'ventas_anuladas': anuladas,
        'ventas_dia': ventas_dia,
        'total_vendido': total_vendido,
        'total_efectivo': desglose['efectivo'],
        'total_tarjeta': desglose['tarjeta'],
        'num_ventas': ventas.count(),
        'num_anuladas': anuladas.count(),
        'productos_vendidos': productos_vendidos,
        'total_abonos': total_abonos,
        'abonos_por_metodo': abonos_por_metodo,
        'num_abonos': num_abonos,
    }


def datos_dashboard(usuario=None):
    """Datos del dashboard. TODAS las consultas de dinero filtran
    estado='completada' para cuadrar exacto con el cierre diario.

    Si se pasa `usuario` (cajero), devuelve la versión reducida con solo sus
    números del día. Si no, la versión completa con gráficas."""
    hoy = timezone.localdate()
    base = Venta.objects.filter(estado=Venta.Estado.COMPLETADA)
    if usuario is not None:
        base = base.filter(usuario=usuario)

    hoy_qs = base.filter(creado__date=hoy)
    total_hoy = hoy_qs.aggregate(t=Coalesce(Sum('total'), Decimal('0.00')))['t']
    ultimas = (
        hoy_qs.select_related('cliente', 'usuario')
        .prefetch_related('detalles__producto')
        .order_by('-creado')[:10]
    )

    stock_bajo = list(
        Producto.objects.filter(activo=True, stock__lte=Producto.STOCK_BAJO_UMBRAL)
        .select_related('categoria').order_by('stock')
    )

    datos = {
        'total_hoy': total_hoy,
        'num_ventas_hoy': hoy_qs.count(),
        'productos_hoy': DetalleVenta.objects.filter(venta__in=hoy_qs)
            .aggregate(c=Coalesce(Sum('cantidad'), 0))['c'],
        'ultimas_ventas': ultimas,
        'stock_bajo': stock_bajo,
        'num_stock_bajo': len(stock_bajo),
    }

    if usuario is not None:
        datos['reducido'] = True
        return datos

    # ---- Gráficas (últimos 7 días) ----
    dias = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
    ventas_semana = base.filter(creado__date__gte=dias[0])
    por_dia = {d: Decimal('0.00') for d in dias}
    for fila in (ventas_semana.values('creado__date')
                 .annotate(t=Coalesce(Sum('total'), Decimal('0.00')))):
        por_dia[fila['creado__date']] = fila['t']
    datos['chart_semana'] = {
        'labels': [d.strftime('%d/%m') for d in dias],
        'valores': [float(por_dia[d]) for d in dias],
    }

    top = (
        DetalleVenta.objects
        .filter(venta__estado=Venta.Estado.COMPLETADA)
        .values('producto__nombre', 'producto__modelo', 'producto__color')
        .annotate(cant=Sum('cantidad'))
        .order_by('-cant')[:5]
    )
    def _nombre(f):
        partes = [f['producto__nombre']]
        if f['producto__modelo']:
            partes.append(f['producto__modelo'])
        if f['producto__color']:
            partes.append(f['producto__color'])
        return ' - '.join(partes)
    datos['chart_top'] = {
        'labels': [_nombre(f) for f in top],
        'valores': [f['cant'] for f in top],
    }

    por_cajero = (
        base.values('usuario__username')
        .annotate(t=Coalesce(Sum('total'), Decimal('0.00')))
        .order_by('-t')
    )
    datos['chart_cajero'] = {
        'labels': [f['usuario__username'] for f in por_cajero],
        'valores': [float(f['t']) for f in por_cajero],
    }
    datos['reducido'] = False
    return datos
