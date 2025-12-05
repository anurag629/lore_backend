from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class LoreUserManager(BaseUserManager):
    """
    Custom user manager for LoreUser.
    Uses wallet_address instead of username.
    """
    
    def create_user(self, wallet_address, email=None, password=None, **extra_fields):
        """Create and save a regular user with the given wallet address."""
        if not wallet_address:
            raise ValueError('The wallet_address must be set')
        
        # Handle email: normalize if provided, set to None if empty/None
        if email and email.strip():
            email = self.normalize_email(email)
        else:
            email = None
        
        user = self.model(wallet_address=wallet_address, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user
    
    def create_superuser(self, wallet_address, email=None, password=None, **extra_fields):
        """Create and save a superuser with the given wallet address."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        if not password:
            raise ValueError('Superuser must have a password.')
        
        return self.create_user(wallet_address, email, password, **extra_fields)


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

    # Override email to make it optional
    email = models.EmailField(
        blank=True,
        null=True,
        help_text="Email address (optional)"
    )

    # Use wallet_address as the unique identifier for login
    USERNAME_FIELD = 'wallet_address'
    REQUIRED_FIELDS = []  # No required fields beyond wallet_address
    
    # Use custom manager
    objects = LoreUserManager()

    bio = models.TextField(
        blank=True,
        help_text="User bio/description"
    )

    avatar_url = models.URLField(
        blank=True,
        help_text="Profile avatar URL"
    )

    banner_url = models.URLField(
        blank=True,
        help_text="Profile banner/cover image URL"
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
        indexes = [
            models.Index(fields=['wallet_address']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.username or self.wallet_address[:10]

    @property
    def display_name(self):
        """Return username if set, otherwise shortened wallet address"""
        return self.username or f"{self.wallet_address[:6]}...{self.wallet_address[-4:]}"
