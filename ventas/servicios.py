"""Lógica de negocio de ventas.

Regla de oro #2 y #3: toda la operación va dentro de transaction.atomic()
con select_for_update() sobre productos y cliente, y TODOS los montos se
recalculan en el backend validando contra la base. Nunca se confía en el
frontend.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction

from clientes.models import Cliente
from productos.models import Producto
from usuarios.models import RegistroActividad, registrar_actividad

from .models import DetalleVenta, Venta

CENTAVO = Decimal('0.01')


class ErrorVenta(Exception):
    """Error de validación al crear una venta (mensaje apto para el usuario)."""


def _a_decimal(valor, campo):
    try:
        return Decimal(str(valor)).quantize(CENTAVO)
    except (InvalidOperation, TypeError, ValueError):
        raise ErrorVenta(f'Valor inválido en {campo}.')


def _a_entero(valor, campo):
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErrorVenta(f'Valor inválido en {campo}.')


@transaction.atomic
def crear_venta(usuario, *, cliente_id=None, nombre_cliente_libre='', telefono='',
                metodo_pago='efectivo', monto_tarjeta=None, aplicar_saldo=False,
                lineas=None):
    """Crea una venta de forma atómica. Devuelve la Venta o lanza ErrorVenta.

    `lineas`: lista de dicts {producto_id, cantidad, precio_unitario}.
    """
    lineas = lineas or []
    if not lineas:
        raise ErrorVenta('La venta no tiene productos.')

    if metodo_pago not in dict(Venta.MetodoPago.choices):
        raise ErrorVenta('Método de pago inválido.')

    # 1. Bloquear los productos involucrados (select_for_update).
    ids = []
    for ln in lineas:
        ids.append(_a_entero(ln.get('producto_id'), 'producto'))
    productos = {
        p.id: p
        for p in Producto.objects.select_for_update().filter(id__in=ids)
    }

    detalles = []
    subtotal_cobrado = Decimal('0.00')
    descuento_total = Decimal('0.00')

    # Agrupa cantidades por producto para validar contra el stock real total.
    for ln in lineas:
        pid = _a_entero(ln.get('producto_id'), 'producto')
        cantidad = _a_entero(ln.get('cantidad'), 'cantidad')
        precio_unitario = _a_decimal(ln.get('precio_unitario'), 'precio')

        producto = productos.get(pid)
        if producto is None:
            raise ErrorVenta('Uno de los productos no existe.')
        if not producto.activo:
            raise ErrorVenta(f'El producto «{producto.nombre_completo}» está inactivo.')
        if cantidad < 1:
            raise ErrorVenta('La cantidad debe ser al menos 1.')
        if cantidad > producto.stock:
            raise ErrorVenta(
                f'Stock insuficiente de «{producto.nombre_completo}» '
                f'(disponible: {producto.stock}).')
        # Solo se puede BAJAR el precio (descuento), nunca subirlo.
        if precio_unitario < 0:
            raise ErrorVenta('El precio no puede ser negativo.')
        if precio_unitario > producto.precio:
            raise ErrorVenta(
                f'El precio de «{producto.nombre_completo}» no puede superar '
                f'el precio de lista (Q {producto.precio}).')

        precio_original = producto.precio
        sub = (precio_unitario * cantidad).quantize(CENTAVO)
        subtotal_cobrado += sub
        descuento_total += ((precio_original - precio_unitario) * cantidad).quantize(CENTAVO)
        detalles.append({
            'producto': producto,
            'cantidad': cantidad,
            'precio_original': precio_original,
            'precio_unitario': precio_unitario,
            'subtotal': sub,
        })

    subtotal_cobrado = subtotal_cobrado.quantize(CENTAVO)
    descuento_total = descuento_total.quantize(CENTAVO)

    # 2. Saldo a favor del cliente (si aplica), con lock sobre el cliente.
    cliente = None
    saldo_aplicado = Decimal('0.00')
    if cliente_id:
        cliente = Cliente.objects.select_for_update().filter(id=cliente_id).first()
        if cliente is None:
            raise ErrorVenta('El cliente seleccionado no existe.')
        if aplicar_saldo and cliente.saldo_favor > 0:
            # Capeado a min(saldo, subtotal cobrado). Nunca deja total negativo.
            saldo_aplicado = min(cliente.saldo_favor, subtotal_cobrado).quantize(CENTAVO)
            cliente.saldo_favor = (cliente.saldo_favor - saldo_aplicado).quantize(CENTAVO)
            cliente.save(update_fields=['saldo_favor'])

    # 3. Total final (recalculado en backend).
    total = (subtotal_cobrado - saldo_aplicado).quantize(CENTAVO)

    monto_tarjeta_val = None
    if metodo_pago == Venta.MetodoPago.TARJETA:
        # Informativo: monto que indica la terminal. Si no viene, usa el total.
        monto_tarjeta_val = (
            _a_decimal(monto_tarjeta, 'monto de tarjeta')
            if monto_tarjeta not in (None, '') else total
        )

    # 4. Persistir venta + detalles y descontar stock.
    venta = Venta.objects.create(
        cliente=cliente,
        nombre_cliente_libre='' if cliente else (nombre_cliente_libre or '').strip(),
        telefono=(telefono or '').strip(),
        usuario=usuario,
        metodo_pago=metodo_pago,
        monto_tarjeta=monto_tarjeta_val,
        saldo_aplicado=saldo_aplicado,
        subtotal=subtotal_cobrado,
        descuento_total=descuento_total,
        total=total,
    )
    for d in detalles:
        DetalleVenta.objects.create(venta=venta, **d)
        producto = d['producto']
        producto.stock -= d['cantidad']
        producto.save(update_fields=['stock'])

    # 5. Registrar actividad si hubo descuento o saldo aplicado.
    if descuento_total > 0:
        registrar_actividad(
            usuario, RegistroActividad.Tipo.DESCUENTO,
            f'Descuento de Q {descuento_total} en la venta #{venta.pk}',
            venta_id=venta.pk, descuento=descuento_total)
    if saldo_aplicado > 0:
        registrar_actividad(
            usuario, RegistroActividad.Tipo.SALDO,
            f'Aplicó Q {saldo_aplicado} de saldo del cliente en la venta #{venta.pk}',
            venta_id=venta.pk, cliente_id=cliente.pk, saldo_aplicado=saldo_aplicado)

    return venta
