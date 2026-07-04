from django import forms

from productos.forms import BootstrapMixin

from .models import Cliente


class ClienteForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        # El saldo a favor NO se edita a mano: lo mueven las ventas,
        # anulaciones y apartados dentro de transacciones controladas.
        fields = ('nombre', 'telefono', 'direccion')
