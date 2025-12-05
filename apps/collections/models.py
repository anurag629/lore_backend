from django.db import models
from django.conf import settings


class Collection(models.Model):
    """
    A curated collection of IP assets created by users.
    Users can organize their favorite assets into collections.
    """
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='collections',
        help_text="User who created this collection"
    )

    title = models.CharField(
        max_length=255,
        help_text="Collection title"
    )

    description = models.TextField(
        blank=True,
        help_text="Collection description"
    )

    cover_image_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL to collection cover image"
    )

    is_public = models.BooleanField(
        default=True,
        help_text="Whether collection is publicly visible"
    )

    assets = models.ManyToManyField(
        'assets.IPAsset',
        related_name='collections',
        blank=True,
        help_text="IP assets in this collection"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['is_public', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} by {self.creator.display_name}"

    @property
    def asset_count(self):
        """Get number of assets in collection."""
        return self.assets.filter(is_deleted=False).count()


class Favorite(models.Model):
    """
    User favorites/bookmarks for IP assets.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
        help_text="User who favorited the asset"
    )

    asset = models.ForeignKey(
        'assets.IPAsset',
        on_delete=models.CASCADE,
        related_name='favorites',
        help_text="Asset that was favorited"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"
        ordering = ['-created_at']
        unique_together = [['user', 'asset']]  # Prevent duplicate favorites
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['asset', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.display_name} favorited {self.asset.title}"

