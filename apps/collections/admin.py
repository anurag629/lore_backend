from django.contrib import admin
from .models import Collection, Favorite


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    """Admin interface for Collections."""
    list_display = ['id', 'title', 'creator', 'asset_count', 'is_public', 'created_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['title', 'description', 'creator__wallet_address']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['creator']
    filter_horizontal = ['assets']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Admin interface for Favorites."""
    list_display = ['id', 'user', 'asset', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__wallet_address', 'user__display_name', 'asset__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'asset']

