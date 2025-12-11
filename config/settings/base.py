"""
Django settings for Lore project.
Base settings shared across all environments.
"""

from pathlib import Path
import environ

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environment variables
env = environ.Env(
    DEBUG=(bool, False)
)

# Read .env file
environ.Env.read_env(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')  # No default - must be set explicitly
# Debug mode - should be False in production
DEBUG = env.bool('DEBUG', default=False)

# Allowed hosts - must be configured when DEBUG=False
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',

    # Local apps
    'apps.core.apps.CoreConfig',
    'apps.assets.apps.AssetsConfig',
    'apps.ai.apps.AIConfig',
    'apps.collections.apps.CollectionsConfig',
    'apps.social.apps.SocialConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'core.LoreUser'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',      # Anonymous users
        'user': '1000/hour',     # Authenticated users
        'ai': '50/hour',         # AI endpoints (more restrictive)
        'upload': '10/hour',     # File uploads
        'token_refresh': '10/minute',  # Token refresh rate limiting
    },
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# drf-spectacular settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'Lore API',
    'DESCRIPTION': 'API documentation for Lore - IP Asset Management Platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'TAGS': [
        {'name': 'Authentication', 'description': 'SIWE authentication endpoints'},
        {'name': 'IP Assets', 'description': 'IP asset management endpoints'},
        {'name': 'AI Features', 'description': 'AI-powered content generation endpoints'},
        {'name': 'Health', 'description': 'System health check endpoints'},
    ],
}

# JWT Configuration
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# Web3 Configuration
WEB3_PROVIDER_URI = env('WEB3_PROVIDER_URI', default='https://aeneid.storyrpc.io')
STORY_PROTOCOL_CHAIN_ID = env.int('STORY_PROTOCOL_CHAIN_ID', default=1315)
BLOCKCHAIN_RECEIPT_TIMEOUT = env.int('BLOCKCHAIN_RECEIPT_TIMEOUT', default=120)  # seconds
BLOCKCHAIN_RPC_TIMEOUT = env.int('BLOCKCHAIN_RPC_TIMEOUT', default=30)  # seconds for RPC calls

# Circuit Breaker Configuration
CIRCUIT_BREAKER_ENABLED = env.bool('CIRCUIT_BREAKER_ENABLED', default=True)
CIRCUIT_BREAKER_IPFS_THRESHOLD = env.int('CIRCUIT_BREAKER_IPFS_THRESHOLD', default=3)
CIRCUIT_BREAKER_IPFS_TIMEOUT = env.int('CIRCUIT_BREAKER_IPFS_TIMEOUT', default=30)
CIRCUIT_BREAKER_BLOCKCHAIN_THRESHOLD = env.int('CIRCUIT_BREAKER_BLOCKCHAIN_THRESHOLD', default=5)
CIRCUIT_BREAKER_BLOCKCHAIN_TIMEOUT = env.int('CIRCUIT_BREAKER_BLOCKCHAIN_TIMEOUT', default=60)
CIRCUIT_BREAKER_AI_THRESHOLD = env.int('CIRCUIT_BREAKER_AI_THRESHOLD', default=3)
CIRCUIT_BREAKER_AI_TIMEOUT = env.int('CIRCUIT_BREAKER_AI_TIMEOUT', default=45)

# Story Protocol Configuration
STORY_PROTOCOL_PRIVATE_KEY = env('STORY_PROTOCOL_PRIVATE_KEY', default='')
STORY_PROTOCOL_NETWORK = env('STORY_PROTOCOL_NETWORK', default='aeneid')  # aeneid (testnet) or mainnet
STORY_PROTOCOL_SPG_NFT_CONTRACT = env('STORY_PROTOCOL_SPG_NFT_CONTRACT', default='0xfE265a91dBe911db06999019228a678b86C04959')  # Default SPG NFT contract for Aeneid testnet

# IPFS / Pinata Configuration
PINATA_API_KEY = env('PINATA_API_KEY', default='')
PINATA_SECRET_KEY = env('PINATA_SECRET_KEY', default='')

# ===== AI / LiteLLM Configuration =====
OPENROUTER_API_KEY = env('OPENROUTER_API_KEY', default='')

# Model configuration (free tier)
AI_MODELS = {
    'fast': [
        'google/gemini-flash-1.5',
        'meta-llama/llama-3.2-3b-instruct',
        'mistralai/mistral-7b-instruct',
    ],
    'quality': [
        'google/gemini-pro-1.5',
        'meta-llama/llama-3.1-8b-instruct',
    ],
}

DEFAULT_AI_MODEL = env('DEFAULT_AI_MODEL', default='google/gemini-flash-1.5')
AI_MAX_TOKENS = env.int('AI_MAX_TOKENS', default=500)
AI_TEMPERATURE = env.float('AI_TEMPERATURE', default=0.7)
AI_REQUEST_TIMEOUT = env.int('AI_REQUEST_TIMEOUT', default=30)
AI_CACHE_ENABLED = env.bool('AI_CACHE_ENABLED', default=True)
AI_CACHE_TTL = env.int('AI_CACHE_TTL', default=3600)  # 1 hour

# File Upload Configuration
MAX_FILE_SIZE = env.int('MAX_FILE_SIZE', default=50 * 1024 * 1024)  # 50MB default

# Logging Configuration
import os
logs_dir = BASE_DIR / 'logs'
os.makedirs(logs_dir, exist_ok=True)

# Check if python-json-logger is available
try:
    import pythonjsonlogger.jsonlogger
    JSON_FORMATTER_AVAILABLE = True
except ImportError:
    JSON_FORMATTER_AVAILABLE = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(logs_dir / 'django.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',  # Use verbose formatter (works without extra packages)
        },
        'console': {
            'level': 'DEBUG' if env('DEBUG', default=False) else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.assets': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.core': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
        },
    },
}

# Add JSON formatter if python-json-logger is available
if JSON_FORMATTER_AVAILABLE:
    LOGGING['formatters']['json'] = {
        '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
        'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
    }
    # Optionally switch file handler to JSON formatter
    # LOGGING['handlers']['file']['formatter'] = 'json'

# Validate settings on startup
# NOTE: Validation is called at the end of local.py/production.py after all settings are finalized
# from config.settings.validator import validate_settings_on_startup
# validate_settings_on_startup()
