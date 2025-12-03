from django.contrib.auth.models import AbstractUser
from django.db import models


class LoreUser(AbstractUser):
    """
    Custom user model for Lore platform.
    Uses wallet address as the primary authentication method.
    """
    wallet_address = models.CharField(
        max_length=42,
        unique=True,
        db_index=True,
        help_text="Ethereum wallet address (0x...)"
    )

    # Override username to make it optional (wallet is primary identifier)
    username = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Display name (optional)"
    )

    # Use wallet_address as the unique identifier for login
    USERNAME_FIELD = 'wallet_address'
    REQUIRED_FIELDS = ['email']  # email is still required for createsuperuser

    bio = models.TextField(
        blank=True,
        help_text="User bio/description"
    )

    avatar_url = models.URLField(
        blank=True,
        help_text="Profile avatar URL"
    )

    total_earnings = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        default=0,
        help_text="Total royalty earnings in ETH"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lore User"
        verbose_name_plural = "Lore Users"
        ordering = ['-created_at']

    def __str__(self):
        return self.username or self.wallet_address[:10]

    @property
    def display_name(self):
        """Return username if set, otherwise shortened wallet address"""
        return self.username or f"{self.wallet_address[:6]}...{self.wallet_address[-4:]}"
