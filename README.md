# Lore Backend

Django REST API for IP asset management on Story Protocol with AI-powered content generation.

## Quick Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file in `lore_backend/` directory:

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/lore_db

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000

# Story Protocol (Aeneid Testnet)
STORY_PROTOCOL_CHAIN_ID=1315
WEB3_PROVIDER_URI=https://aeneid.storyrpc.io
STORY_PROTOCOL_PRIVATE_KEY=0xyour-private-key-here
STORY_PROTOCOL_NETWORK=aeneid

# Pinata IPFS
PINATA_API_KEY=your-pinata-api-key
PINATA_SECRET_KEY=your-pinata-secret-key

# AI / OpenRouter (for AI features)
OPENROUTER_API_KEY=your-openrouter-api-key

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7
```

### 3. Setup Database

```bash
# Create PostgreSQL database
createdb lore_db

# Run migrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser
```

### 4. Run Server

```bash
python manage.py runserver
```

Server runs at `http://localhost:8000`

## API Endpoints

- **Auth:** `/api/auth/`
  - POST `/nonce/` - Get SIWE message
  - POST `/login/` - Login with wallet signature
  - POST `/logout/` - Logout
  - GET `/me/` - Get current user

- **Assets:** `/api/assets/`
  - GET `/assets/` - List all assets
  - POST `/assets/` - Create new asset
  - GET `/assets/{id}/` - Get asset details
  - POST `/assets/{id}/derivatives/` - Create derivative (supports multi-parent)
  - GET `/assets/{id}/royalty_balance/` - Check royalty balance
  - POST `/assets/{id}/claim_royalties/` - Claim royalties
  - GET `/assets/{id}/royalty_payments/` - Payment history for an asset
  - GET `/royalty_payments/{id}/` - Royalty payment detail

- **Group IP:** `/api/groups/`
  - GET `/groups/` - List group IPs
  - POST `/groups/` - Create group IP
  - GET `/groups/{id}/` - Get group IP detail
  - PATCH `/groups/{id}/` - Update group IP metadata
  - POST `/groups/{id}/register/` - Register group on-chain
  - POST `/groups/{id}/members/` - Add member (asset-based)
  - DELETE `/groups/{id}/members/{member_id}/` - Remove member
  - GET `/groups/{id}/statistics/` - Group stats
  - GET `/groups/{id}/distributions/` - Royalty distributions

- **Disputes:** `/api/disputes/`
  - GET `/disputes/` - List disputes with filters
  - POST `/disputes/` - Raise dispute for an asset
  - GET `/disputes/{id}/` - Dispute detail
  - POST `/disputes/{id}/evidence/` - Submit evidence
  - POST `/disputes/{id}/resolve/` - Resolve dispute (admin)
  - POST `/disputes/{id}/cancel/` - Cancel dispute (disputer)
  - GET `/disputes/{id}/statistics/` - Dispute stats

- **Permissions:** `/api/permissions/`
  - GET `/permissions/` - List permissions
  - POST `/permissions/` - Grant/override permission
  - GET `/permissions/{id}/` - Permission detail
  - POST `/permissions/{id}/revoke/` - Revoke permission
  - POST `/permissions/revoke_all/` - Revoke all for an asset
  - GET `/permissions/asset/{asset_id}/` - Permissions for asset
  - GET `/permissions/summary/{asset_id}/` - Summary/checks for asset

- **AI Features:** `/api/assets/ai/`
  - POST `/generate-title/` - Generate title suggestions
  - POST `/enhance-description/` - Enhance brief description
  - POST `/analyze-content/` - Extract categories and tags
  - POST `/suggest-license/` - Recommend license terms
  - POST `/analyze-derivative/` - Analyze derivative similarity
  - GET `/usage-stats/` - Get user AI usage statistics
  - GET `/platform-stats/` - Get platform-wide AI stats (admin only)

- **API Docs:** `/api/docs/` - Swagger UI

## Key Files

```
lore_backend/
├── apps/
│   ├── core/              # User models & authentication (SIWE)
│   └── assets/            # IP assets, Story Protocol & AI
│       ├── models.py      # IPAsset, AIGenerationLog, AIAssetMetadata
│       ├── ai_service.py  # AI service with LiteLLM integration
│       ├── views.py       # API endpoints (includes AI endpoints)
│       ├── serializers.py # Request/response serializers
│       └── admin.py       # Django admin interfaces
├── config/
│   └── settings/
│       └── base.py        # Django settings (includes AI config)
├── manage.py
└── requirements/
    └── base.txt           # Dependencies (includes litellm)
```

## AI Features

The backend includes AI-powered content generation using free LLM models via OpenRouter:

### 1. Title Generation
- Generates 4 creative title suggestions (50-70 characters)
- Input: Brief description + asset type
- Uses fast models (Google Gemini Flash, Llama, Mistral)

### 2. Description Enhancement
- Expands brief descriptions into detailed 150-200 word narratives
- Input: Brief description, optional title
- Uses fast models with creative temperature

### 3. Content Analysis
- Auto-categorizes assets and extracts tags
- Input: Title + description
- Returns: Category, tags, art style, theme, genre
- Uses quality models for better accuracy

### 4. License Suggestions
- Recommends optimal royalty percentage and rights
- Input: Asset type, description, intended use
- Returns: Royalty %, derivatives flag, commercial rights + reasoning

### 5. Derivative Analysis
- Analyzes similarity between parent and derivative assets
- Input: Parent + derivative descriptions
- Returns: Similarity score, transformation type, attribution

### Architecture
- **Service Layer:** `ai_service.py` (singleton pattern)
- **Caching:** Redis with MD5-based keys (3600s TTL)
- **Fallback Logic:** Auto-switches models when rate limited
- **Database Tracking:** Full audit trail in `AIGenerationLog`
- **Analytics:** User stats & platform stats endpoints

## Getting API Keys

**OpenRouter (AI Features):**
1. Sign up at https://openrouter.ai
2. Create API key (free tier available)
3. Add `OPENROUTER_API_KEY` to `.env` file
4. Free models: Gemini Flash, Llama 3.2, Mistral 7B

**Pinata (IPFS):**
1. Sign up at https://pinata.cloud
2. Generate API key in dashboard
3. Add to `.env` file

**Story Protocol:**
1. Create new wallet in MetaMask
2. Export private key
3. Get testnet tokens from Story faucet
4. Add private key to `.env` file

## Common Commands

```bash
# Run server
python manage.py runserver

# Make migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Django shell
python manage.py shell

# Run tests
python manage.py test
```

## User Management

### Make an Existing User Staff/Superuser

If you've already signed in with your wallet and need admin access, use the Django shell:

```bash
python manage.py shell
```

Then run:

```python
from apps.core.models import LoreUser

# Find your user by wallet address (lowercase)
user = LoreUser.objects.get(wallet_address='0xyour_wallet_address_here'.lower())

# Make the user staff (can access Django admin)
user.is_staff = True

# Make the user superuser (full admin privileges)
user.is_superuser = True

# Set a password for Django admin login (optional but recommended)
user.set_password('your_secure_password_here')

# Save changes
user.save()

# Verify
print(f"User: {user.wallet_address}")
print(f"is_staff: {user.is_staff}")
print(f"is_superuser: {user.is_superuser}")
print(f"has_password: {user.has_usable_password()}")
```

> **Note:** After setting a password, you can log into Django admin (`/admin/`) using your wallet address as the username and the password you set.

### List All Users

```python
from apps.core.models import LoreUser

# List all users
for user in LoreUser.objects.all():
    print(f"{user.wallet_address} - staff: {user.is_staff}, super: {user.is_superuser}")
```

### Change/Reset Password

```python
from apps.core.models import LoreUser

user = LoreUser.objects.get(wallet_address='0xyour_wallet_address_here'.lower())
user.set_password('new_secure_password')
user.save()
```

### Remove Admin Privileges

```python
user = LoreUser.objects.get(wallet_address='0xyour_wallet_address_here'.lower())
user.is_staff = False
user.is_superuser = False
user.save()
```

After making yourself a superuser, you can access the Django admin at `http://localhost:8000/admin/`

## Tech Stack

- **Backend Framework:** Django 5.1
- **API Framework:** Django REST Framework 3.15
- **Database:** PostgreSQL with JSONField support
- **Caching:** Redis 5.0
- **Blockchain:** Story Protocol Python SDK 0.1.0
- **IPFS Storage:** Pinata
- **Authentication:** JWT with SIWE (Sign-In With Ethereum)
- **AI/ML:** LiteLLM 1.35+ with OpenRouter
- **Task Queue:** Celery 5.3

## Troubleshooting

**Server won't start:**
- Check virtual environment is activated
- Verify `.env` file exists
- Ensure PostgreSQL is running

**Database errors:**
- Create database: `createdb lore_db`
- Run migrations: `python manage.py migrate`

**CORS errors:**
- Add frontend URL to `CORS_ALLOWED_ORIGINS` in `.env`
- Restart server after changes

**AI features not working:**
- Check `OPENROUTER_API_KEY` is set in `.env`
- Verify key is valid at https://openrouter.ai
- Check Redis is running: `redis-cli ping` should return `PONG`
- Test in Django shell:
  ```python
  from apps.assets.ai_service import get_ai_service
  service = get_ai_service()
  service.is_ready()  # Should return True
  ```

**Rate limiting errors:**
- Free models have rate limits (60 req/min)
- Service auto-switches to fallback models
- Check cache: AI responses are cached for 1 hour
- View logs in Django admin: `/admin/assets/aigenerationlog/`
