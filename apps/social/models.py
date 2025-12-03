from django.db import models
from django.conf import settings
from apps.assets.models import IPAsset


class Interaction(models.Model):
    """
    Tracks user interactions with IP assets.
    Includes likes, views, and spin-off registrations.
    """
    INTERACTION_TYPES = [
        ('like', 'Like'),
        ('view', 'View'),
        ('spinoff', 'Spin-off'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interactions',
        help_text="User who performed the interaction"
    )

    asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='interactions',
        help_text="Asset being interacted with"
    )

    type = models.CharField(
        max_length=20,
        choices=INTERACTION_TYPES,
        help_text="Type of interaction"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Interaction"
        verbose_name_plural = "Interactions"
        ordering = ['-created_at']
        # Prevent duplicate likes from same user
        unique_together = [['user', 'asset', 'type']]

    def __str__(self):
        return f"{self.user.display_name} {self.type} {self.asset.title}"
