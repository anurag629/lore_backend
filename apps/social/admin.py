"""
Admin configuration for social models.
"""
from django.contrib import admin
from .models import Comment, Interaction


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """Admin interface for Comment model."""
    list_display = ['id', 'user', 'asset', 'parent', 'content_preview', 'is_deleted', 'created_at']
    list_filter = ['is_deleted', 'created_at', 'asset']
    search_fields = ['content', 'user__wallet_address', 'user__display_name', 'asset__title']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']
    raw_id_fields = ['user', 'asset', 'parent']
    
    def content_preview(self, obj):
        """Show truncated content."""
        if obj.content:
            return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
        return '-'
    content_preview.short_description = 'Content'


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    """Admin interface for Interaction model."""
    list_display = ['id', 'user', 'asset', 'type', 'created_at']
    list_filter = ['type', 'created_at']
    search_fields = ['user__wallet_address', 'user__display_name', 'asset__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'asset']

