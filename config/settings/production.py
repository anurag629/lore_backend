"""
Production settings for Azure deployment
"""

from .base import *
import dj_database_url
import os

DEBUG = False

# Azure App Service will set these
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[
    '*.azurewebsites.net',
    'lore-backend.azurewebsites.net',
    '.localhost',
    '127.0.0.1',
])

# Database - Using Azure PostgreSQL
# Azure provides AZURE_POSTGRESQL_CONNECTIONSTRING, convert to DATABASE_URL format if needed
azure_conn_string = os.environ.get('AZURE_POSTGRESQL_CONNECTIONSTRING', '')
database_url = env('DATABASE_URL', default='')

if azure_conn_string and not database_url:
    # Parse Azure's connection string format:
    # dbname=xxx host=xxx port=xxx sslmode=require user=xxx password=xxx
    conn_parts = {}
    for part in azure_conn_string.split():
        if '=' in part:
            key, value = part.split('=', 1)
            conn_parts[key] = value

    # Convert to DATABASE_URL format
    database_url = f"postgres://{conn_parts.get('user', '')}:{conn_parts.get('password', '')}@{conn_parts.get('host', '')}:{conn_parts.get('port', '5432')}/{conn_parts.get('dbname', '')}"

DATABASES = {
    'default': dj_database_url.config(
        default=database_url,
        conn_max_age=600,
        ssl_require=True,
    )
}

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# HTTPS settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# CORS settings
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# Azure health check middleware - must be FIRST to handle health checks before host validation
MIDDLEWARE.insert(0, 'config.middleware.AzureHealthCheckMiddleware')

# Static files - Using Whitenoise (insert after SecurityMiddleware)
MIDDLEWARE.insert(2, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files - Using Pinata/IPFS (same as local)
# Pinata credentials are already loaded from base.py:
# - PINATA_API_KEY
# - PINATA_SECRET_KEY
# Media files are uploaded directly to IPFS via Pinata in the asset creation flow.

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': env('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}

# Validate settings after all overrides are applied
from config.settings.validator import validate_settings_on_startup
validate_settings_on_startup()
