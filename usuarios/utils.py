"""Utilidades compartidas entre vistas de las distintas apps."""


def _entero_o_none(valor):
    """Convierte un parámetro GET a int; None si viene vacío o con basura.

    Mismo espíritu que los helpers _fecha/_decimal del historial de ventas:
    un filtro con valor no numérico simplemente se ignora, en vez de reventar
    con un 500 (ValueError) al armar el queryset.
    """
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
