"""Filtro de formato monetario del sistema.

Con LANGUAGE_CODE='es' los Decimal se localizan como "1000,00" (coma
decimal, sin miles). El negocio usa SIEMPRE "Q 1,000.00": miles con coma
y decimales con punto, igual en pantalla y en los PDF.
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def quetzal(valor):
    """Formatea un monto como 'Q 1,000.00'."""
    try:
        n = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return valor
    return f'Q {n:,.2f}'
