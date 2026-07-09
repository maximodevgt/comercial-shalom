from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, ListView, UpdateView,
)

from usuarios.models import RegistroActividad, registrar_actividad
from usuarios.permisos import SoloAdminMixin
from usuarios.utils import _entero_o_none

from .forms import CategoriaForm, ProductoForm
from .models import Categoria, Producto

# ─────────────────────────── Productos ───────────────────────────

class ProductoListView(LoginRequiredMixin, ListView):
    model = Producto
    template_name = 'productos/lista.html'
    context_object_name = 'productos'
    paginate_by = 50

    def get_queryset(self):
        qs = Producto.objects.select_related('categoria')
        # TODO (B-8, solo a gran escala): las búsquedas icontains de acá (y de
        # clientes/proveedores) escanean la tabla; con decenas de miles de
        # filas conviene GinIndex + pg_trgm (requiere CREATE EXTENSION en la
        # BD, coordinar con el despliegue).
        q = self.request.GET.get('q', '').strip()
        # Un valor no numérico se ignora en vez de romper con 500 (M-4).
        categoria = _entero_o_none(self.request.GET.get('categoria'))
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(modelo__icontains=q)
                | Q(color__icontains=q)
            )
        if categoria:
            qs = qs.filter(categoria_id=categoria)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categorias'] = Categoria.objects.all()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['categoria_sel'] = self.request.GET.get('categoria', '')
        return ctx


class ProductoCreateView(SoloAdminMixin, CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'productos/form.html'
    success_url = reverse_lazy('productos:lista')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, 'Producto creado correctamente.')
        return respuesta


class ProductoUpdateView(SoloAdminMixin, UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'productos/form.html'
    success_url = reverse_lazy('productos:lista')

    def form_valid(self, form):
        # Captura valores anteriores para registrar cambios de precio/stock.
        anterior = Producto.objects.get(pk=self.object.pk)
        precio_anterior = anterior.precio
        stock_anterior = anterior.stock

        respuesta = super().form_valid(form)

        cambios = {}
        if self.object.precio != precio_anterior:
            cambios['precio'] = {
                'anterior': str(precio_anterior), 'nuevo': str(self.object.precio),
            }
        if self.object.stock != stock_anterior:
            cambios['stock'] = {
                'anterior': stock_anterior, 'nuevo': self.object.stock,
            }
        if cambios:
            registrar_actividad(
                self.request.user,
                RegistroActividad.Tipo.PRODUCTO,
                f'Editó el producto «{self.object.nombre_completo}»',
                producto_id=self.object.pk,
                **cambios,
            )
        messages.success(self.request, 'Producto actualizado correctamente.')
        return respuesta


class ProductoDeleteView(SoloAdminMixin, DeleteView):
    model = Producto
    template_name = 'productos/confirmar_eliminar.html'
    success_url = reverse_lazy('productos:lista')
    context_object_name = 'objeto'

    def form_valid(self, form):
        producto = self.get_object()
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'No se puede eliminar «{producto.nombre_completo}» porque '
                'tiene ventas o apartados asociados. Podés desactivarlo en su lugar.',
            )
            return redirect('productos:lista')
        registrar_actividad(
            self.request.user,
            RegistroActividad.Tipo.PRODUCTO,
            f'Eliminó el producto «{producto.nombre_completo}»',
            producto_id=producto.pk,
            precio=str(producto.precio),
            stock=producto.stock,
        )
        messages.success(self.request, 'Producto eliminado.')
        return respuesta


# ─────────────────────────── Categorías ───────────────────────────

class CategoriaListView(LoginRequiredMixin, ListView):
    model = Categoria
    template_name = 'productos/categorias.html'
    context_object_name = 'categorias'
    paginate_by = 50


class CategoriaCreateView(SoloAdminMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'productos/form.html'
    success_url = reverse_lazy('productos:categorias')

    def form_valid(self, form):
        messages.success(self.request, 'Categoría creada correctamente.')
        return super().form_valid(form)


class CategoriaUpdateView(SoloAdminMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'productos/form.html'
    success_url = reverse_lazy('productos:categorias')

    def form_valid(self, form):
        messages.success(self.request, 'Categoría actualizada correctamente.')
        return super().form_valid(form)


class CategoriaDeleteView(SoloAdminMixin, DeleteView):
    model = Categoria
    template_name = 'productos/confirmar_eliminar.html'
    success_url = reverse_lazy('productos:categorias')
    context_object_name = 'objeto'

    def form_valid(self, form):
        categoria = self.get_object()
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'No se puede eliminar la categoría «{categoria.nombre}» '
                'porque tiene productos asociados.',
            )
            return redirect('productos:categorias')
        messages.success(self.request, 'Categoría eliminada.')
        return respuesta
