import json
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from clientes.models import Cliente
from productos.models import Categoria, Producto
from usuarios.models import Usuario
from usuarios.permisos import RolRequeridoMixin, rol_requerido

from .models import Venta
from .servicios import ErrorAnulacion, ErrorVenta, anular_venta, crear_venta


class PuedeVenderMixin(RolRequeridoMixin):
    """Vender: cajero y admin (supervisor no)."""

    roles_permitidos = (Usuario.Rol.CAJERO,)


class PosView(PuedeVenderMixin, TemplateView):
    template_name = 'ventas/pos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        productos = Producto.objects.select_related('categoria').filter(activo=True)
        ctx['categorias'] = Categoria.objects.all()
        ctx['clientes'] = Cliente.objects.all()
        # Datos para el grid del POS (se leen desde JS con json_script).
        ctx['productos_data'] = [
            {
                'id': p.id,
                'nombre': p.nombre,
                'modelo': p.modelo,
                'color': p.color,
                'nombre_completo': p.nombre_completo,
                'precio': str(p.precio),
                'stock': p.stock,
                'categoria_id': p.categoria_id,
                'foto': p.foto.url if p.foto else '',
            }
            for p in productos
        ]
        # Saldos de clientes para mostrar el saldo disponible al elegirlo.
        ctx['clientes_saldo'] = {c.id: str(c.saldo_favor) for c in ctx['clientes']}
        return ctx


@rol_requerido(Usuario.Rol.CAJERO)
@require_POST
def registrar_venta(request):
    """Recibe la venta como JSON, la crea en el backend y devuelve el resultado."""
    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Datos inválidos.'}, status=400)

    try:
        venta = crear_venta(
            request.user,
            cliente_id=datos.get('cliente_id') or None,
            nombre_cliente_libre=datos.get('nombre_cliente_libre', ''),
            telefono=datos.get('telefono', ''),
            metodo_pago=datos.get('metodo_pago', 'efectivo'),
            monto_tarjeta=datos.get('monto_tarjeta'),
            aplicar_saldo=bool(datos.get('aplicar_saldo')),
            lineas=datos.get('lineas', []),
        )
    except ErrorVenta as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)

    return JsonResponse({'ok': True, 'venta_id': venta.pk})


class HistorialVentasView(LoginRequiredMixin, ListView):
    template_name = 'ventas/historial.html'
    context_object_name = 'ventas'
    paginate_by = 50

    def get_queryset(self):
        qs = (
            Venta.objects
            .select_related('cliente', 'usuario')
            .prefetch_related('detalles__producto')
        )
        u = self.request.user
        # El cajero SOLO ve sus propias ventas (no configurable).
        if u.es_cajero and not u.es_admin:
            qs = qs.filter(usuario=u)

        # Filtro por cajero (solo lo aplican admin/supervisor).
        cajero = self.request.GET.get('cajero', '').strip()
        if cajero and (u.es_admin or u.es_supervisor):
            qs = qs.filter(usuario_id=cajero)

        desde, hasta = self._rango_fechas()
        if desde:
            qs = qs.filter(creado__date__gte=desde)
        if hasta:
            qs = qs.filter(creado__date__lte=hasta)

        minimo = self._decimal(self.request.GET.get('min'))
        maximo = self._decimal(self.request.GET.get('max'))
        if minimo is not None:
            qs = qs.filter(total__gte=minimo)
        if maximo is not None:
            qs = qs.filter(total__lte=maximo)

        self.qs_filtrado = qs
        return qs

    def _rango_fechas(self):
        """Rango (desde, hasta) del filtro de fecha; fija self.periodo_label.

        Por defecto —sin desde/hasta ni ?todas— el historial muestra SOLO hoy,
        para no confundir el total del histórico con el del día. ?todas=1 quita
        el filtro de fecha (histórico completo); desde/hasta arman un rango.
        """
        self.es_hoy = False
        if self.request.GET.get('todas'):
            self.periodo_label = 'Todas las ventas'
            return None, None

        desde = self._fecha(self.request.GET.get('desde'))
        hasta = self._fecha(self.request.GET.get('hasta'))

        # Sin rango explícito: por defecto, solo el día de hoy (zona local).
        if desde is None and hasta is None:
            hoy = timezone.localdate()
            self.es_hoy = True
            self.periodo_label = f'Hoy — {hoy:%d/%m/%Y}'
            return hoy, hoy

        if desde and hasta:
            self.periodo_label = (
                f'Día {desde:%d/%m/%Y}' if desde == hasta
                else f'Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}')
        elif desde:
            self.periodo_label = f'Desde el {desde:%d/%m/%Y}'
        else:
            self.periodo_label = f'Hasta el {hasta:%d/%m/%Y}'
        return desde, hasta

    @staticmethod
    def _fecha(valor):
        if not valor:
            return None
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _decimal(valor):
        if not valor:
            return None
        try:
            return Decimal(valor)
        except Exception:
            return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.qs_filtrado
        cero = DecimalField(max_digits=12, decimal_places=2)
        # Totales GLOBALES sobre el queryset filtrado completo (no la página).
        completadas = qs.filter(estado=Venta.Estado.COMPLETADA)
        ctx['total_vendido'] = completadas.aggregate(
            t=Coalesce(Sum('total'), Decimal('0'), output_field=cero))['t']
        ctx['num_completadas'] = completadas.count()
        ctx['num_anuladas'] = qs.filter(estado=Venta.Estado.ANULADA).count()

        u = self.request.user
        ctx['puede_filtrar_cajero'] = u.es_admin or u.es_supervisor
        if ctx['puede_filtrar_cajero']:
            ctx['cajeros'] = Usuario.objects.filter(rol=Usuario.Rol.CAJERO)
        ctx['filtros'] = self.request.GET
        # Período que se está viendo (calculado en _rango_fechas) para aclarar
        # a qué corresponden los totales y resaltar el botón "Hoy".
        ctx['periodo_label'] = self.periodo_label
        ctx['es_hoy'] = self.es_hoy
        return ctx


class VentaDetailView(LoginRequiredMixin, DetailView):
    model = Venta
    template_name = 'ventas/detalle.html'
    context_object_name = 'venta'

    def get_object(self, queryset=None):
        venta = get_object_or_404(
            Venta.objects.select_related('cliente', 'usuario')
            .prefetch_related('detalles__producto'),
            pk=self.kwargs['pk'],
        )
        u = self.request.user
        # El cajero solo puede ver sus propias ventas.
        if u.es_cajero and not u.es_admin and venta.usuario_id != u.id:
            raise PermissionDenied('No podés ver ventas de otros cajeros.')
        return venta


@rol_requerido()  # solo admin (permitir_admin=True por defecto)
def anular_venta_view(request, pk):
    """Anula una venta. Requiere motivo obligatorio. Solo admin."""
    venta = get_object_or_404(Venta, pk=pk)
    if request.method == 'POST':
        try:
            anular_venta(request.user, pk, request.POST.get('motivo', ''))
            messages.success(request, f'Venta #{pk} anulada correctamente.')
        except ErrorAnulacion as e:
            messages.error(request, str(e))
        return redirect('ventas:detalle', pk=pk)
    return render(request, 'ventas/anular.html', {'venta': venta})
