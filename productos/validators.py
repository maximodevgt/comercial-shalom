"""Validaciones para las fotos de producto (regla de oro #10)."""
from django.core.exceptions import ValidationError

EXTENSIONES_PERMITIDAS = ('jpg', 'jpeg', 'png', 'webp')
CONTENT_TYPES_PERMITIDOS = ('image/jpeg', 'image/png', 'image/webp')
TAMANO_MAXIMO_MB = 5
TAMANO_MAXIMO_BYTES = TAMANO_MAXIMO_MB * 1024 * 1024


def validar_foto_producto(archivo):
    """Valida extensión (jpg/jpeg/png/webp, NO svg) y tamaño (<= 5MB)."""
    nombre = getattr(archivo, 'name', '') or ''
    extension = nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValidationError(
            'Formato de imagen no permitido. Usá JPG, JPEG, PNG o WEBP '
            '(los SVG no están permitidos).'
        )

    # content_type puede no estar disponible en todos los backends de storage.
    content_type = getattr(archivo, 'content_type', None)
    if content_type and content_type not in CONTENT_TYPES_PERMITIDOS:
        raise ValidationError('El tipo de archivo de la imagen no es válido.')

    tamano = getattr(archivo, 'size', None)
    if tamano is not None and tamano > TAMANO_MAXIMO_BYTES:
        raise ValidationError(
            f'La imagen no puede superar los {TAMANO_MAXIMO_MB} MB.'
        )
