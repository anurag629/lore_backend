from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
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


class Comment(models.Model):
    """
    User comments on IP assets.
    Supports nested replies (threaded comments).
    """
    asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="Asset this comment is on"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="User who wrote the comment"
    )

    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies',
        help_text="Parent comment if this is a reply"
    )

    content = models.TextField(
        max_length=2000,
        help_text="Comment content"
    )

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag"
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when comment was deleted"
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Comment"
        verbose_name_plural = "Comments"
        ordering = ['created_at']  # Oldest first for threaded display
        indexes = [
            models.Index(fields=['asset', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['parent', '-created_at']),
            models.Index(fields=['is_deleted', '-created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.user.display_name} on {self.asset.title}"

    def clean(self):
        """Validate comment."""
        if self.parent and self.parent.asset != self.asset:
            raise ValidationError("Reply must be on the same asset as parent comment.")
        if self.parent and self.parent.is_deleted:
            raise ValidationError("Cannot reply to a deleted comment.")

    @property
    def reply_count(self):
        """Count of replies to this comment."""
        return self.replies.filter(is_deleted=False).count()

    def soft_delete(self):
        """Soft delete the comment."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])
