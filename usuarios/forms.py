from django import forms
from django.contrib.auth.password_validation import validate_password

from productos.forms import BootstrapMixin

from .models import Usuario

DOMINIO_CORREO = '@comercialshalom.com'


class _CorreoDominioMixin:
    """Valida el correo como usuario + dominio fijo @comercialshalom.com."""

    def clean_correo_usuario(self):
        local = (self.cleaned_data.get('correo_usuario') or '').strip().lower()
        if not local:
            raise forms.ValidationError('Ingresá la parte del correo antes del @.')
        if '@' in local or ' ' in local:
            raise forms.ValidationError('Escribí solo la parte antes del @ (sin espacios).')
        email = local + DOMINIO_CORREO
        qs = Usuario.objects.filter(email__iexact=email)
        if getattr(self, 'instance', None) and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con ese correo.')
        return local

    @property
    def email_completo(self):
        return self.cleaned_data['correo_usuario'] + DOMINIO_CORREO


class UsuarioCrearForm(_CorreoDominioMixin, BootstrapMixin, forms.ModelForm):
    correo_usuario = forms.CharField(label='Correo', max_length=100)
    password = forms.CharField(
        label='Contraseña', widget=forms.PasswordInput,
        help_text='Mínimo 8 caracteres; no puede ser solo numérica ni demasiado común.')

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'rol')

    def clean_password(self):
        password = self.cleaned_data.get('password')
        validate_password(password)
        return password

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.email_completo
        usuario.set_password(self.cleaned_data['password'])
        if commit:
            usuario.save()
        return usuario


class UsuarioEditarForm(BootstrapMixin, forms.ModelForm):
    """Editar usuario: el correo NO se edita; se puede cambiar rol y resetear
    la contraseña (opcional)."""

    password = forms.CharField(
        label='Nueva contraseña (opcional)', widget=forms.PasswordInput,
        required=False,
        help_text='Dejá en blanco para no cambiarla. Mínimo 8 caracteres.')

    class Meta:
        model = Usuario
        fields = ('first_name', 'last_name', 'rol')

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if self.cleaned_data.get('password'):
            usuario.set_password(self.cleaned_data['password'])
        if commit:
            usuario.save()
        return usuario
