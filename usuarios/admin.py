from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin del usuario personalizado, con el campo `rol` incluido."""

    list_display = ('username', 'first_name', 'last_name', 'rol', 'is_active', 'is_staff')
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')

    # Agrega la sección de rol a los fieldsets heredados de UserAdmin.
    fieldsets = UserAdmin.fieldsets + (
        ('Rol en el sistema', {'fields': ('rol',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rol en el sistema', {'fields': ('rol',)}),
    )
