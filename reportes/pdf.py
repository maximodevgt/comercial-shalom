"""Generación de PDFs con xhtml2pdf (pure-python, sin dependencias de sistema).

Todas las vistas que generan PDF deben envolver render_pdf() en try/except y,
ante un fallo, mostrar un mensaje amigable y redirigir (nunca un 500)."""
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa


class ErrorPDF(Exception):
    pass


def render_pdf(template_name, context, nombre_archivo='documento.pdf'):
    """Renderiza un template a PDF y devuelve un HttpResponse descargable.

    Lanza ErrorPDF si la generación falla."""
    html = render_to_string(template_name, context)
    buffer = BytesIO()
    resultado = pisa.CreatePDF(src=html, dest=buffer, encoding='utf-8')
    if resultado.err:
        raise ErrorPDF('No se pudo generar el PDF.')
    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="{nombre_archivo}"'
    return respuesta
