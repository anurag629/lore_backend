from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import LoreUser


@admin.register(LoreUser)
class LoreUserAdmin(UserAdmin):
    """Admin interface for LoreUser"""

    list_display = ['wallet_address', 'username', 'email', 'total_earnings', 'created_at']
    list_filter = ['is_staff', 'is_superuser', 'created_at']
    search_fields = ['wallet_address', 'username', 'email']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('wallet_address', 'password')}),
        ('Personal info', {'fields': ('username', 'email', 'bio', 'avatar_url')}),
        ('Earnings', {'fields': ('total_earnings',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('wallet_address', 'username', 'email', 'password1', 'password2'),
        }),
    )
