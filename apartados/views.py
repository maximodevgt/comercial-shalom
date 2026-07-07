from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from clientes.models import Cliente
from productos.models import Producto
from usuarios.models import Usuario
from usuarios.permisos import rol_requerido

from .models import Abono, Apartado
from .servicios import (
    ErrorApartado, cancelar_apartado, crear_apartado, liquidar_apartado,
    registrar_abono,
)


def _puede_ver(usuario, apartado):
    return not (usuario.es_cajero and not usuario.es_admin
                and apartado.usuario_id != usuario.id)


class ApartadoListView(LoginRequiredMixin, ListView):
    template_name = 'apartados/lista.html'
    context_object_name = 'apartados'
    paginate_by = 50

    def get_queryset(self):
        # Anotación en vez de prefetch_related('abonos'): total_abonado/pendiente
        # la usan directo y se evita el N+1 (un aggregate por fila) del listado.
        qs = (Apartado.objects.select_related('producto', 'cliente', 'usuario')
              .annotate(_total_abonado=Coalesce(Sum('abonos__monto'), Decimal('0'))))
        u = self.request.user
        if u.es_cajero and not u.es_admin:
            qs = qs.filter(usuario=u)
        estado = self.request.GET.get('estado', '').strip()
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['estados'] = Apartado.Estado.choices
        ctx['estado_sel'] = self.request.GET.get('estado', '')
        return ctx


class ApartadoDetailView(LoginRequiredMixin, DetailView):
    template_name = 'apartados/detalle.html'
    context_object_name = 'apartado'

    def get_object(self, queryset=None):
        apartado = get_object_or_404(
            Apartado.objects.select_related('producto', 'cliente', 'usuario', 'venta')
            .prefetch_related('abonos__usuario'),
            pk=self.kwargs['pk'])
        if not _puede_ver(self.request.user, apartado):
            raise PermissionDenied('No podés ver apartados de otros cajeros.')
        return apartado

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['metodos'] = Abono.Metodo.choices
        ctx['clientes'] = Cliente.objects.all()
        return ctx


@rol_requerido(Usuario.Rol.CAJERO)
def crear_apartado_view(request):
    if request.method == 'POST':
        try:
            apartado = crear_apartado(
                request.user,
                producto_id=request.POST.get('producto'),
                precio_total=request.POST.get('precio_total'),
                cliente_id=request.POST.get('cliente') or None,
                nombre_cliente_libre=request.POST.get('nombre_cliente_libre', ''),
                telefono=request.POST.get('telefono', ''),
                direccion=request.POST.get('direccion', ''),
                abono_inicial=request.POST.get('abono_inicial', '0'),
                metodo_abono=request.POST.get('metodo_abono', Abono.Metodo.EFECTIVO),
            )
            messages.success(request, f'Apartado #{apartado.pk} creado.')
            return redirect('apartados:detalle', pk=apartado.pk)
        except ErrorApartado as e:
            messages.error(request, str(e))

    productos = Producto.objects.select_related('categoria').filter(activo=True, stock__gt=0)
    clientes = Cliente.objects.all()
    return render(request, 'apartados/form.html', {
        'clientes': clientes,
        'productos_data': [
            {'id': p.id, 'nombre_completo': p.nombre_completo, 'precio': str(p.precio),
             'stock': p.stock, 'foto': p.foto.url if p.foto else ''}
            for p in productos
        ],
        'clientes_saldo': {c.id: str(c.saldo_favor) for c in clientes},
    })


@rol_requerido(Usuario.Rol.CAJERO)
@require_POST
def abonar_view(request, pk):
    apartado = get_object_or_404(Apartado, pk=pk)
    if not _puede_ver(request.user, apartado):
        raise PermissionDenied()
    try:
        registrar_abono(request.user, pk, request.POST.get('monto'),
                        request.POST.get('metodo', Abono.Metodo.EFECTIVO))
        messages.success(request, 'Abono registrado.')
    except ErrorApartado as e:
        messages.error(request, str(e))
    return redirect('apartados:detalle', pk=pk)


@rol_requerido(Usuario.Rol.CAJERO)
@require_POST
def liquidar_view(request, pk):
    apartado = get_object_or_404(Apartado, pk=pk)
    if not _puede_ver(request.user, apartado):
        raise PermissionDenied()
    try:
        venta = liquidar_apartado(request.user, pk)
        messages.success(request, f'Apartado liquidado. Venta #{venta.pk} generada.')
        return redirect('ventas:detalle', pk=venta.pk)
    except ErrorApartado as e:
        messages.error(request, str(e))
        return redirect('apartados:detalle', pk=pk)


@rol_requerido()  # solo admin: redirige dinero abonado (saldo/pérdida), igual que anular_venta
@require_POST
def cancelar_view(request, pk):
    apartado = get_object_or_404(Apartado, pk=pk)
    try:
        cancelar_apartado(
            request.user, pk,
            destino=request.POST.get('destino', 'saldo_cliente'),
            cliente_destino_id=request.POST.get('cliente_destino') or None,
            nuevo_cliente={
                'nombre': request.POST.get('nuevo_nombre', ''),
                'telefono': request.POST.get('nuevo_telefono', ''),
                'direccion': request.POST.get('nuevo_direccion', ''),
            },
        )
        messages.success(request, 'Apartado cancelado.')
    except ErrorApartado as e:
        messages.error(request, str(e))
    return redirect('apartados:detalle', pk=pk)
