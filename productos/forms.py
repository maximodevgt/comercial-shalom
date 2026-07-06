from django import forms

from .models import Categoria, Producto


class BootstrapMixin:
    """Aplica clases de Bootstrap 5 a los widgets del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault('class', 'form-control')
            else:
                widget.attrs.setdefault('class', 'form-control')


class CategoriaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ('nombre',)


class ProductoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = (
            'categoria', 'proveedor', 'nombre', 'modelo', 'color',
            'precio', 'stock', 'activo', 'foto',
        )
        widgets = {
            'precio': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'stock': forms.NumberInput(attrs={'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Proveedor opcional (queryset ya ordenado por empresa vía Meta).
        self.fields['proveedor'].empty_label = '— Sin proveedor —'

    def clean_precio(self):
        precio = self.cleaned_data['precio']
        if precio is not None and precio < 0:
            raise forms.ValidationError('El precio no puede ser negativo.')
        return precio
