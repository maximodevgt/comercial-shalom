from django import forms

from productos.forms import BootstrapMixin

from .models import Proveedor


class ProveedorForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ('empresa', 'nombre', 'telefono', 'email', 'direccion', 'notas')
        widgets = {'notas': forms.Textarea(attrs={'rows': 3})}
