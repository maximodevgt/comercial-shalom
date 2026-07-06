"""Lógica de negocio de apartados. Todo con transaction.atomic() y locks
(reglas de oro #1 y #2)."""
from decimal import Decimal, InvalidOperation

from django.db import transaction

from clientes.models import Cliente
from productos.models import Producto
from usuarios.models import RegistroActividad, registrar_actividad
from ventas.models import DetalleVenta, Venta

from .models import Abono, Apartado

CENTAVO = Decimal('0.01')


class ErrorApartado(Exception):
    """Error de negocio en apartados (mensaje apto para el usuario)."""


def _dec(valor, campo, permitir_cero=True):
    try:
        d = Decimal(str(valor)).quantize(CENTAVO)
    except (InvalidOperation, TypeError, ValueError):
        raise ErrorApartado(f'Valor inválido en {campo}.')
    if d < 0 or (not permitir_cero and d == 0):
        raise ErrorApartado(f'Valor inválido en {campo}.')
    return d


@transaction.atomic
def crear_apartado(usuario, *, producto_id, precio_total, cliente_id=None,
                   nombre_cliente_libre='', telefono='', direccion='',
                   abono_inicial='0', metodo_abono=Abono.Metodo.EFECTIVO):
    """Crea un apartado, descuenta 1 unidad de stock y registra el abono
    inicial opcional. Devuelve el Apartado o lanza ErrorApartado."""
    producto = Producto.objects.select_for_update().filter(id=producto_id).first()
    if producto is None:
        raise ErrorApartado('El producto no existe.')
    if producto.stock < 1:
        raise ErrorApartado(f'No hay stock de «{producto.nombre_completo}».')

    precio_original = producto.precio
    precio_total = _dec(precio_total, 'precio total', permitir_cero=False)
    # El precio total solo puede BAJAR respecto al de lista (descuento).
    if precio_total > precio_original:
        raise ErrorApartado(
            f'El precio del apartado no puede superar el precio de lista '
            f'(Q {precio_original}).')

    cliente = None
    if cliente_id:
        cliente = Cliente.objects.select_for_update().filter(id=cliente_id).first()
        if cliente is None:
            raise ErrorApartado('El cliente seleccionado no existe.')

    # Descontar 1 unidad de stock.
    producto.stock -= 1
    producto.save(update_fields=['stock'])

    apartado = Apartado.objects.create(
        cliente=cliente,
        nombre_cliente_libre='' if cliente else (nombre_cliente_libre or '').strip(),
        telefono=(telefono or '').strip(),
        direccion=(direccion or '').strip(),
        producto=producto,
        precio_original=precio_original,
        precio_total=precio_total,
        usuario=usuario,
    )

    monto_inicial = _dec(abono_inicial or '0', 'abono inicial')
    if monto_inicial > 0:
        _registrar_abono(usuario, apartado, monto_inicial, metodo_abono, cliente)

    registrar_actividad(
        usuario, RegistroActividad.Tipo.APARTADO,
        f'Creó el apartado #{apartado.pk} de «{producto.nombre_completo}»',
        apartado_id=apartado.pk, precio_total=precio_total)
    return apartado


def _registrar_abono(usuario, apartado, monto, metodo, cliente):
    """Crea un abono. Con efectivo/tarjeta el monto NO puede superar el
    pendiente: capear en silencio dejaba dinero recibido sin registrar
    (descuadre de caja); se rechaza para que el cajero corrija y dé el
    cambio. Con saldo sí se capea a min(saldo, pendiente): no hay efectivo
    físico de por medio. Asume apartado ya bloqueado."""
    pendiente = apartado.pendiente
    if pendiente <= 0:
        raise ErrorApartado('El apartado ya está totalmente pagado.')

    monto = monto.quantize(CENTAVO)
    if monto <= 0:
        raise ErrorApartado('El monto del abono debe ser mayor a 0.')

    if metodo == Abono.Metodo.SALDO:
        if cliente is None:
            raise ErrorApartado('No hay cliente registrado para usar saldo.')
        if cliente.saldo_favor <= 0:
            raise ErrorApartado('El cliente no tiene saldo a favor.')
        monto = min(monto, pendiente, cliente.saldo_favor).quantize(CENTAVO)
        cliente.saldo_favor = (cliente.saldo_favor - monto).quantize(CENTAVO)
        cliente.save(update_fields=['saldo_favor'])
    elif monto > pendiente:
        raise ErrorApartado(
            f'El abono (Q {monto}) supera el saldo pendiente (Q {pendiente}). '
            f'Ingresá el monto correcto y entregá el cambio.')

    return Abono.objects.create(
        apartado=apartado, monto=monto, metodo=metodo, usuario=usuario)


@transaction.atomic
def registrar_abono(usuario, apartado_id, monto, metodo=Abono.Metodo.EFECTIVO):
    """Registra un abono posterior sobre un apartado activo."""
    apartado = (
        # of=('self',): bloquea solo el apartado; Postgres no permite FOR UPDATE
        # sobre el outer join del select_related (cliente es nullable).
        Apartado.objects.select_for_update(of=('self',)).select_related('cliente')
        .filter(id=apartado_id).first())
    if apartado is None:
        raise ErrorApartado('El apartado no existe.')
    if apartado.estado != Apartado.Estado.ACTIVO:
        raise ErrorApartado('Solo se puede abonar a un apartado activo.')

    cliente = None
    if apartado.cliente_id:
        cliente = Cliente.objects.select_for_update().get(pk=apartado.cliente_id)

    monto = _dec(monto, 'abono', permitir_cero=False)
    abono = _registrar_abono(usuario, apartado, monto, metodo, cliente)
    return abono


@transaction.atomic
def liquidar_apartado(usuario, apartado_id):
    """Liquida un apartado saldado: crea la Venta correspondiente (sin volver
    a tocar el stock, ya descontado al crear) y lo marca liquidado."""
    apartado = (
        Apartado.objects.select_for_update(of=('self',))
        .select_related('cliente', 'producto')
        .filter(id=apartado_id).first())
    if apartado is None:
        raise ErrorApartado('El apartado no existe.')
    if apartado.estado != Apartado.Estado.ACTIVO:
        raise ErrorApartado('Este apartado ya no está activo.')
    if apartado.pendiente > 0:
        raise ErrorApartado(
            f'El apartado aún tiene un saldo pendiente de Q {apartado.pendiente}.')

    venta = Venta.objects.create(
        cliente=apartado.cliente,
        nombre_cliente_libre=apartado.nombre_cliente_libre,
        telefono=apartado.telefono,
        usuario=usuario,
        metodo_pago=Venta.MetodoPago.EFECTIVO,
        saldo_aplicado=Decimal('0.00'),
        subtotal=apartado.precio_total,
        descuento_total=apartado.descuento,
        total=apartado.precio_total,
    )
    DetalleVenta.objects.create(
        venta=venta,
        producto=apartado.producto,
        cantidad=1,
        precio_original=apartado.precio_original,
        precio_unitario=apartado.precio_total,
        subtotal=apartado.precio_total,
    )

    apartado.estado = Apartado.Estado.LIQUIDADO
    apartado.venta = venta
    apartado.save(update_fields=['estado', 'venta', 'actualizado'])

    registrar_actividad(
        usuario, RegistroActividad.Tipo.APARTADO,
        f'Liquidó el apartado #{apartado.pk} → venta #{venta.pk}',
        apartado_id=apartado.pk, venta_id=venta.pk, total=apartado.precio_total)
    return venta


@transaction.atomic
def cancelar_apartado(usuario, apartado_id, *, destino='saldo_cliente',
                      cliente_destino_id=None, nuevo_cliente=None):
    """Cancela un apartado activo: restaura el stock y convierte lo abonado en
    saldo a favor.

    `destino` (cuando NO hay cliente registrado en el apartado):
      - 'cliente_existente': acredita a `cliente_destino_id`.
      - 'cliente_nuevo': crea el cliente con `nuevo_cliente` (dict) y le acredita.
      - 'perdida': registra la devolución en efectivo / pérdida (no crea saldo).
    Si el apartado tiene cliente, siempre se le acredita a ese cliente.
    """
    apartado = (
        Apartado.objects.select_for_update(of=('self',))
        .select_related('cliente', 'producto')
        .filter(id=apartado_id).first())
    if apartado is None:
        raise ErrorApartado('El apartado no existe.')
    if apartado.estado != Apartado.Estado.ACTIVO:
        raise ErrorApartado('Este apartado ya no está activo.')

    # Restaurar stock (lock sobre el producto).
    producto = Producto.objects.select_for_update().get(pk=apartado.producto_id)
    producto.stock += 1
    producto.save(update_fields=['stock'])

    abonado = apartado.total_abonado
    detalle_destino = destino

    if abonado > 0:
        cliente = None
        if apartado.cliente_id:
            cliente = Cliente.objects.select_for_update().get(pk=apartado.cliente_id)
            detalle_destino = 'saldo_cliente'
        elif destino == 'cliente_existente' and cliente_destino_id:
            cliente = Cliente.objects.select_for_update().filter(id=cliente_destino_id).first()
            if cliente is None:
                raise ErrorApartado('El cliente destino no existe.')
        elif destino == 'cliente_nuevo' and nuevo_cliente:
            cliente = Cliente.objects.create(
                nombre=(nuevo_cliente.get('nombre') or '').strip() or 'Cliente',
                telefono=(nuevo_cliente.get('telefono') or '').strip(),
                direccion=(nuevo_cliente.get('direccion') or '').strip())
        elif destino == 'perdida':
            cliente = None
        else:
            raise ErrorApartado('Indicá qué hacer con lo abonado.')

        if cliente is not None:
            cliente.saldo_favor = (cliente.saldo_favor + abonado).quantize(CENTAVO)
            cliente.save(update_fields=['saldo_favor'])

    apartado.estado = Apartado.Estado.CANCELADO
    apartado.save(update_fields=['estado', 'actualizado'])

    registrar_actividad(
        usuario, RegistroActividad.Tipo.APARTADO,
        f'Canceló el apartado #{apartado.pk}',
        apartado_id=apartado.pk, abonado=abonado, destino=detalle_destino)
    return apartado
