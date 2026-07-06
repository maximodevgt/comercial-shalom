from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apartados.models import Abono, Apartado
from usuarios.models import Usuario
from usuarios.permisos import RolRequeridoMixin
from ventas.models import Venta

from .consultas import resumen_dia
from .pdf import ErrorPDF, render_pdf

NEGOCIO = {
    'nombre': 'Comercial Shalom',
    'direccion': 'Guatemala',
    # xhtml2pdf necesita la ruta ABSOLUTA del archivo (no la URL estática).
    'logo': finders.find('img/logo.png'),
}


def _fecha(valor, por_defecto=None):
    if valor:
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except ValueError:
            pass
    return por_defecto or timezone.localdate()


class CierreDiarioView(LoginRequiredMixin, TemplateView):
    """Cierre del día. Admin/supervisor ven todo; el cajero ve solo lo suyo."""
    template_name = 'reportes/cierre.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        usuario = u if (u.es_cajero and not u.es_admin) else None
        ctx.update(resumen_dia(timezone.localdate(), usuario=usuario))
        ctx['solo_propias'] = usuario is not None
        return ctx


class ReporteFechaView(RolRequeridoMixin, TemplateView):
    """Reporte por fecha. Solo admin y supervisor."""
    roles_permitidos = (Usuario.Rol.SUPERVISOR,)
    template_name = 'reportes/reporte.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fecha = _fecha(self.request.GET.get('fecha'))
        ctx.update(resumen_dia(fecha))
        ctx['fecha_str'] = fecha.strftime('%Y-%m-%d')
        return ctx


# ─────────────────────────── PDFs ───────────────────────────

def _pdf_o_redirect(request, template, contexto, nombre, destino):
    """Genera un PDF; si falla, muestra mensaje amigable y redirige."""
    try:
        return render_pdf(template, contexto, nombre)
    except (ErrorPDF, Exception):
        messages.error(request, 'No se pudo generar el PDF. Intentá de nuevo.')
        return redirect(destino)


def ticket_venta_pdf(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied()
    venta = get_object_or_404(
        Venta.objects.select_related('cliente', 'usuario').prefetch_related('detalles__producto'), pk=pk)
    u = request.user
    if u.es_cajero and not u.es_admin and venta.usuario_id != u.id:
        raise PermissionDenied()
    return _pdf_o_redirect(
        request, 'reportes/pdf/ticket_venta.html',
        {'venta': venta, 'negocio': NEGOCIO}, f'ticket_venta_{pk}.pdf',
        'ventas:detalle')


def comprobante_abono_pdf(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied()
    abono = get_object_or_404(
        Abono.objects.select_related('apartado__producto', 'apartado__cliente', 'usuario'), pk=pk)
    return _pdf_o_redirect(
        request, 'reportes/pdf/comprobante_abono.html',
        {'abono': abono, 'apartado': abono.apartado, 'negocio': NEGOCIO},
        f'comprobante_abono_{pk}.pdf', 'apartados:lista')


def ticket_liquidacion_pdf(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied()
    apartado = get_object_or_404(
        Apartado.objects.select_related('producto', 'cliente', 'venta').prefetch_related('abonos'), pk=pk)
    return _pdf_o_redirect(
        request, 'reportes/pdf/ticket_liquidacion.html',
        {'apartado': apartado, 'negocio': NEGOCIO}, f'liquidacion_{pk}.pdf',
        'apartados:detalle')


def cierre_pdf(request):
    if not request.user.is_authenticated:
        raise PermissionDenied()
    u = request.user
    usuario = u if (u.es_cajero and not u.es_admin) else None
    ctx = resumen_dia(timezone.localdate(), usuario=usuario)
    ctx['negocio'] = NEGOCIO
    ctx['titulo'] = 'Cierre Diario'
    ctx['cajero_filtro'] = usuario  # el encabezado muestra "Cajero: X" si aplica
    return _pdf_o_redirect(
        request, 'reportes/pdf/cierre.html', ctx,
        f'cierre_{ctx["fecha"]}.pdf', 'reportes:cierre')


def reporte_pdf(request):
    u = request.user
    if not u.is_authenticated:
        raise PermissionDenied()
    if not (u.es_admin or u.es_supervisor):
        raise PermissionDenied()
    fecha = _fecha(request.GET.get('fecha'))
    ctx = resumen_dia(fecha)
    ctx['negocio'] = NEGOCIO
    ctx['titulo'] = 'Reporte de Ventas por Fecha'
    return _pdf_o_redirect(
        request, 'reportes/pdf/cierre.html', ctx,
        f'reporte_{fecha}.pdf', 'reportes:reporte')
