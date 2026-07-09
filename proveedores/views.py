from django.contrib import messages
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView,
)

from usuarios.models import RegistroActividad, registrar_actividad
from usuarios.permisos import SoloAdminMixin

from .forms import ProveedorForm
from .models import Proveedor


class ProveedorListView(SoloAdminMixin, ListView):
    model = Proveedor
    template_name = 'proveedores/lista.html'
    context_object_name = 'proveedores'
    paginate_by = 50

    def get_queryset(self):
        qs = Proveedor.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | Q(empresa__icontains=q)
                | Q(telefono__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ProveedorDetailView(SoloAdminMixin, DetailView):
    model = Proveedor
    template_name = 'proveedores/detalle.html'
    context_object_name = 'proveedor'


class ProveedorCreateView(SoloAdminMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'proveedores/form.html'

    def get_success_url(self):
        return reverse_lazy('proveedores:detalle', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        registrar_actividad(
            self.request.user, RegistroActividad.Tipo.PRODUCTO,
            f'Creó al proveedor «{self.object}»', proveedor_id=self.object.pk)
        messages.success(self.request, 'Proveedor creado correctamente.')
        return respuesta


class ProveedorUpdateView(SoloAdminMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'proveedores/form.html'

    def get_success_url(self):
        return reverse_lazy('proveedores:detalle', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        registrar_actividad(
            self.request.user, RegistroActividad.Tipo.PRODUCTO,
            f'Editó al proveedor «{self.object}»', proveedor_id=self.object.pk)
        messages.success(self.request, 'Proveedor actualizado correctamente.')
        return respuesta


class ProveedorDeleteView(SoloAdminMixin, DeleteView):
    model = Proveedor
    template_name = 'proveedores/confirmar_eliminar.html'
    success_url = reverse_lazy('proveedores:lista')
    context_object_name = 'objeto'

    def form_valid(self, form):
        proveedor = self.get_object()
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'No se puede eliminar a «{proveedor}» porque tiene productos '
                'asociados. Reasigná esos productos primero.',
            )
            return redirect('proveedores:detalle', pk=proveedor.pk)
        registrar_actividad(
            self.request.user, RegistroActividad.Tipo.PRODUCTO,
            f'Eliminó al proveedor «{proveedor}»', proveedor_id=proveedor.pk)
        messages.success(self.request, 'Proveedor eliminado.')
        return respuesta
