from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView,
)

from usuarios.models import Usuario
from usuarios.permisos import RolRequeridoMixin

from .forms import ClienteForm
from .models import Cliente


class AdminOCajeroMixin(RolRequeridoMixin):
    """Crear/editar clientes: admin y cajero (supervisor no)."""

    roles_permitidos = (Usuario.Rol.CAJERO,)


class SoloAdminMixin(RolRequeridoMixin):
    roles_permitidos = ()


class ClienteListView(LoginRequiredMixin, ListView):
    model = Cliente
    template_name = 'clientes/lista.html'
    context_object_name = 'clientes'
    paginate_by = 50

    def get_queryset(self):
        qs = Cliente.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(telefono__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ClienteDetailView(LoginRequiredMixin, DetailView):
    model = Cliente
    template_name = 'clientes/detalle.html'
    context_object_name = 'cliente'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # El historial de ventas y apartados se completa en fases posteriores.
        # Se accede de forma tolerante para no romper antes de esas fases.
        cliente = self.object
        ctx['ventas'] = getattr(cliente, 'ventas', None)
        ctx['apartados'] = getattr(cliente, 'apartados', None)
        return ctx


class ClienteCreateView(AdminOCajeroMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Cliente creado correctamente.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('clientes:detalle', args=[self.object.pk])


class ClienteUpdateView(AdminOCajeroMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Cliente actualizado correctamente.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('clientes:detalle', args=[self.object.pk])


class ClienteDeleteView(SoloAdminMixin, DeleteView):
    model = Cliente
    template_name = 'clientes/confirmar_eliminar.html'
    success_url = reverse_lazy('clientes:lista')
    context_object_name = 'objeto'

    def form_valid(self, form):
        cliente = self.get_object()
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'No se puede eliminar a «{cliente.nombre}» porque tiene '
                'ventas o apartados asociados.',
            )
            return redirect('clientes:detalle', pk=cliente.pk)
        messages.success(self.request, 'Cliente eliminado.')
        return respuesta
