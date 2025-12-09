"""
Settings validator for Lore backend.
Validates required settings and API keys at startup to prevent misconfiguration.
"""
from django.core.exceptions import ImproperlyConfigured
import logging

logger = logging.getLogger(__name__)


class SettingsValidator:
    """
    Validates Django settings to ensure all required configuration is present.

    Provides environment-aware validation - stricter checks in production,
    more lenient in development to allow easier local setup.
    """

    def __init__(self):
        self.errors = []

    def validate_secret_key(self, secret_key):
        """
        Validate that SECRET_KEY is set and not using the default insecure value.

        Args:
            secret_key: The SECRET_KEY from settings

        Raises:
            ImproperlyConfigured: If SECRET_KEY is missing or insecure
        """
        if not secret_key:
            self.errors.append(
                "SECRET_KEY is not set. Set SECRET_KEY environment variable."
            )
        elif secret_key == 'django-insecure-change-this-in-production':
            self.errors.append(
                "SECRET_KEY is using the default insecure value. "
                "Generate a secure key and set it in the SECRET_KEY environment variable."
            )
        elif len(secret_key) < 50:
            self.errors.append(
                f"SECRET_KEY is too short ({len(secret_key)} characters). "
                "Use at least 50 characters for security."
            )

    def validate_api_keys(self, environment='production'):
        """
        Validate that required API keys are present and valid.

        Args:
            environment: 'production' or 'development'

        Raises:
            ImproperlyConfigured: If required keys are missing in production
        """
        from django.conf import settings

        # Story Protocol Private Key
        if environment == 'production':
            if not settings.STORY_PROTOCOL_PRIVATE_KEY:
                self.errors.append(
                    "STORY_PROTOCOL_PRIVATE_KEY is not set. "
                    "Set STORY_PROTOCOL_PRIVATE_KEY environment variable for blockchain operations."
                )
            elif len(settings.STORY_PROTOCOL_PRIVATE_KEY) < 32:
                self.errors.append(
                    "STORY_PROTOCOL_PRIVATE_KEY appears invalid (too short). "
                    "Provide a valid Ethereum private key (64 hex characters)."
                )

        # Pinata API Keys
        if not settings.PINATA_API_KEY:
            level = 'ERROR' if environment == 'production' else 'WARNING'
            message = (
                "PINATA_API_KEY is not set. "
                "File uploads to IPFS will fail. "
                "Set PINATA_API_KEY environment variable."
            )
            if environment == 'production':
                self.errors.append(message)
            else:
                logger.warning(message)

        if not settings.PINATA_SECRET_KEY:
            level = 'ERROR' if environment == 'production' else 'WARNING'
            message = (
                "PINATA_SECRET_KEY is not set. "
                "File uploads to IPFS will fail. "
                "Set PINATA_SECRET_KEY environment variable."
            )
            if environment == 'production':
                self.errors.append(message)
            else:
                logger.warning(message)

        # OpenRouter API Key
        if not settings.OPENROUTER_API_KEY:
            level = 'ERROR' if environment == 'production' else 'WARNING'
            message = (
                "OPENROUTER_API_KEY is not set. "
                "AI features will not work. "
                "Set OPENROUTER_API_KEY environment variable."
            )
            if environment == 'production':
                self.errors.append(message)
            else:
                logger.warning(message)

    def validate_database(self):
        """
        Validate database configuration.

        Raises:
            ImproperlyConfigured: If database is misconfigured
        """
        from django.conf import settings

        databases = getattr(settings, 'DATABASES', {})
        if not databases or 'default' not in databases:
            self.errors.append(
                "DATABASES['default'] is not configured. "
                "Set DATABASE_URL environment variable."
            )

    def validate_cors(self, environment='production'):
        """
        Validate CORS configuration.

        Args:
            environment: 'production' or 'development'

        Raises:
            ImproperlyConfigured: If CORS is misconfigured in production
        """
        from django.conf import settings

        if environment == 'production':
            cors_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
            if not cors_origins:
                self.errors.append(
                    "CORS_ALLOWED_ORIGINS is empty in production. "
                    "Set CORS_ALLOWED_ORIGINS environment variable to allow frontend access."
                )
            elif '*' in cors_origins:
                self.errors.append(
                    "CORS_ALLOWED_ORIGINS contains '*' (allow all) in production. "
                    "Specify explicit origins for security."
                )

    def validate_all(self, environment='production'):
        """
        Run all validation checks.

        Args:
            environment: 'production' or 'development'

        Raises:
            ImproperlyConfigured: If any validation fails
        """
        from django.conf import settings

        self.errors = []  # Reset errors

        logger.info(f"Running settings validation for {environment} environment...")

        # Run all validations
        self.validate_secret_key(settings.SECRET_KEY)
        self.validate_api_keys(environment)
        self.validate_database()
        self.validate_cors(environment)

        # If there are errors, raise exception
        if self.errors:
            error_message = (
                f"Settings validation failed ({len(self.errors)} error(s)):\n\n" +
                "\n".join(f"  - {error}" for error in self.errors) +
                "\n\nPlease check your .env file or environment variables. "
                "See .env.example for required settings."
            )
            raise ImproperlyConfigured(error_message)

        logger.info("✓ All settings validated successfully")


def validate_settings_on_startup():
    """
    Convenience function to run validation on Django startup.

    This should be called at the end of settings files (base.py, production.py, etc.)
    """
    from django.conf import settings

    validator = SettingsValidator()

    # Determine environment
    environment = 'development' if settings.DEBUG else 'production'

    try:
        validator.validate_all(environment=environment)
    except ImproperlyConfigured:
        # Re-raise to stop Django startup
        raise
