# MeeeShop Pinterest Automation — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│              Daily Pinterest Posting Orchestrator                │
│                   (pinterest_daily.py)                          │
└────────┬──────────────────┬──────────────────┬─────────────────┘
         │                  │                  │
    ┌────▼────┐      ┌──────▼──────┐   ┌──────▼──────┐
    │Pinterest │      │   Shopify   │   │ AI Content  │
    │ Client   │      │   Client    │   │ Generator   │
    │(Selenium)│      │ (REST API)  │   │ (Free AI)   │
    └────┬────┘      └──────┬──────┘   └──────┬──────┘
         │                  │                  │
         │              ┌───▼─────────────┐    │
         │              │  Product Fetcher    │    │
         │              │ + Board Mapping ┼────┘
         │              └───┬─────────────┘
         │                  │
    ┌────▼──────────────────▼───────────┐
    │    Posting History (JSON)          │
    │  + Anti-Block Safeguards           │
    │  + Daily Limits & Cooldowns        │
    └────────────────────────────────────┘
```

## Module Breakdown

### 1. **pinterest_client.py** — Web Automation
```
PinterestClient
├── login(email, password) → bool
├── fetch_boards() → Dict[name → id]
├── create_pin(image, title, desc, board, url, alt_text) → bool
└── close()
```

**Technology**: Selenium WebDriver + Chrome
**Why**: No API limits, 100% feature compatibility
**Features**:
- Auto-detect & bypass bot detection
- Headless or interactive mode
- Screenshot debugging on errors
- Automatic board discovery

### 2. **shopify_products.py** — Product Data
```
ShopifyClient
├── get_products(limit, status) → [products]
├── get_collections() → [collections]
└── get_collection_products(id) → [products]

Utilities:
├── format_product_for_pinterest(product) → optimized_data
├── select_board_for_product(data) → board_name
└── get_pinterest_board_mapping() → board_keywords
```

**Integration**: Shopify Admin REST API
**Why**: Direct product access, no rate limits with correct token scopes
**Features**:
- Smart product type matching
- Multi-board routing logic
- Image extraction & validation
- SEO metadata preservation

### 3. **content_generator.py** — AI Content
```
Functions:
├── generate_pinterest_title(product) → str
├── generate_pinterest_description(product, board) → str
├── generate_hashtags(product, board) → [hashtags]
├── generate_keywords_for_seo(product) → [keywords]
└── generate_content_package(product, board) → complete_data
```

**AI Pipeline**:
1. Primary: Gemini 2.0 Flash (1M tokens/day, free)
2. Secondary: Groq Llama-3.3-70B (500K tokens/day, free)
3. Tertiary: OpenRouter 24+ models (unlimited, free)
4. Fallback: Hardcoded templates (no API needed)

**Content Rules**:
- Titles: 100 chars max, power words, emoji-friendly
- Descriptions: 300 chars max, lifestyle benefits, keywords, CTAs
- Hashtags: 10-15 relevant to women fashion, organic growth
- Keywords: 8-12 SEO phrases for Pinterest search

### 4. **ai_client.py** — Free AI Provider
```
Providers (in order):
1. Google Gemini 2.0 Flash
2. Groq Llama-3.3-70B
3. OpenRouter (cascade of 20+ free models)

generate(prompt, max_tokens=400, temperature=0.8) → str | None
```

**Model Categories**:
- SEO: MiniMax M2.5, Qwen3, Llama 3.3 (for content generation)
- Image/Video: Nemotron Omni, Gemma 4, GLM-4.5
- Reasoning: Ring 2.6, Hermes 3, Llama
- Coding: Laguna M.1, Ring 2.6, Qwen3 Coder

**Fallback Behavior**:
- Logs each attempt with timestamp
- Auto-retry on rate limit (429)
- Continues to next model on token limit
- Returns `None` if all fail → caller uses template

### 5. **pinterest_daily.py** — Orchestrator
```
Main Flow:
1. Load history & check daily limits
2. Login to Pinterest
3. Fetch user's boards
4. Fetch products from Shopify
5. Filter out already-posted products
6. Select random product
7. Generate AI content
8. Match to correct board
9. Post to Pinterest
10. Update history & limits

Safety Checks:
├── Daily post count (max 3/day)
├── Cooldown between posts (2+ hours)
├── Board rotation cooldown (24 hours)
├── Already-posted tracking
└── Error recovery & logging
```

**Anti-Block Strategy**:
- **Frequency**: Max 3 pins/day (very safe, tested limit is 5-10/day)
- **Spacing**: 2-hour gaps between posts (mimics organic user)
- **Board Rotation**: Don't post same board twice in 24h (algo flag)
- **Variety**: Random product selection (not predictable patterns)
- **Timing**: Varied timestamps (not always same hour)
- **Content**: Unique titles/descriptions for each post (no spam)

## Data Flow

```
┌──────────────────┐
│ Shopify Products │
└────────┬─────────┘
         │
         ├─→ Filter by collection
         ├─→ Check already posted
         └─→ Random selection
                │
         ┌──────▼──────┐
         │ Format Data │
         └──────┬──────┘
                │
         ┌──────▼────────────┐
         │ AI Content Gen    │
         │ (Gemini/Groq/OR)  │
         └──────┬────────────┘
                │
         ┌──────▼──────┐
         │ Board Match │ (by product type/tags)
         └──────┬──────┘
                │
         ┌──────▼───────────┐
         │ Pinterest Posting │ (Selenium automation)
         └──────┬───────────┘
                │
         ┌──────▼──────┐
         │ Update JSON │ (posting_history)
         │ history     │
         └─────────────┘
```

## State Management

### posting_history.json
```json
{
  "posts": [
    {
      "product_id": "123456",
      "title": "Pin title",
      "board": "Board Name",
      "timestamp": "2026-05-12T14:30:00"
    }
  ],
  "board_last_used": {
    "Board Name": "2026-05-12T14:30:00"
  },
  "daily_count": 1,
  "last_post_time": "2026-05-12T14:30:00"
}
```

**Used for**:
- Tracking posted products (no duplicates within week)
- Daily limit enforcement
- Board rotation cooldown
- Safe resume on failures

## GitHub Actions Integration

```yaml
Daily Posting Workflow:
├─ Trigger: 2 PM UTC daily (or manual)
├─ Runner: ubuntu-latest
├─ Steps:
│  ├─ Checkout code
│  ├─ Setup Python 3.11
│  ├─ Install deps + ChromeDriver
│  ├─ Run pinterest_daily.py
│  ├─ Upload posting_history.json
│  └─ Notify Slack on failure
└─ Secrets: All .env vars from GitHub repo settings
```

## Configuration Hierarchy

```
1. Environment Variables (.env file)
   ├─ PINTEREST_EMAIL
   ├─ PINTEREST_PASSWORD
   ├─ SHOPIFY_STORE_URL
   ├─ SHOPIFY_ACCESS_TOKEN
   ├─ GEMINI_API_KEY (or GROQ/OPENROUTER)
   └─ STORE_BASE_URL

2. Python Constants (in source code)
   ├─ MAX_PINS_PER_DAY (pinterest_daily.py)
   ├─ COOLDOWN_HOURS (pinterest_daily.py)
   ├─ Board mapping (shopify_products.py)
   └─ AI temperature/tokens (content_generator.py)

3. Runtime Decisions
   ├─ Product selection (random from available)
   ├─ Board selection (match by type/tags)
   ├─ AI model selection (fallback cascade)
   └─ Post timing (varies daily)
```

## Resilience Features

### Failure Points & Recovery

| Component | Failure | Recovery |
|-----------|---------|----------|
| Pinterest Login | Wrong creds, 2FA, account locked | Skip run, log error |
| Board Fetch | Network timeout | Retry 3x, use cached |
| Product Fetch | Shopify API down | Retry 3x, skip run |
| AI Generation | All models fail | Use fallback template |
| Image Download | URL broken | Log & skip pin |
| Pin Creation | DOM changed | Log & retry next run |
| File Write | Permission denied | Log & continue |

### Logging

All operations logged with:
- Timestamp
- Component (AI, Selenium, Shopify)
- Success/failure status
- Retry attempts
- Error details (without exposing secrets)

## Performance Considerations

### Token Usage (Per Run)
- AI: 200-400 tokens (Gemini: 1M/day = 2,500+ runs)
- Shopify: ~1KB per product fetch (unlimited with valid token)
- Pinterest: Only browser traffic (no token limits)

### Time Requirements
- Startup: 5-10 sec (browser launch)
- Login: 3-5 sec
- Board fetch: 2-3 sec
- Product fetch: 2-3 sec
- Content generation: 2-5 sec (AI)
- Pin creation: 10-20 sec (UI interaction)
- Total: ~30-50 sec per successful post

### Browser Resource Usage
- RAM: ~300MB (Chrome headless)
- CPU: <5% (mostly waiting for network)
- Disk: ~100MB (cache + videos)

## Scaling Considerations

### If Increasing Frequency

**Safe progression**:
1. Current: 3 pins/day (very safe)
2. Test: 5 pins/day (safe, slight risk)
3. Max: 10 pins/day (risky, high block chance)

**Mitigations for 5+ pins/day**:
- Increase COOLDOWN_HOURS to 3-4
- Stagger posting times across day
- Add human-like randomness to content
- Monitor Pinterest for action blocks
- Have backup boards ready

### Multi-Account Setup

Could extend to:
- Multiple Pinterest accounts
- Scheduled round-robin posting
- Separate board sets per account
- Centralized Shopify product pool

## Dependencies & Versions

```
Core:
- Python 3.10+
- Selenium 4.15+
- WebDriver Manager (auto-downloads ChromeDriver)
- Requests 2.31+
- Python-dotenv 1.0+

External Services:
- Shopify Admin API (2024-01 version)
- Google Gemini / Groq / OpenRouter APIs
- Chrome browser (auto-managed by webdriver-manager)
- Pinterest.com (web browser, no API)
```

## Future Extensions

Potential enhancements:
1. **Video Support**: Use videos from meeeshop-youtube
2. **Rich Pins**: Enhanced product pin format (availability, price)
3. **Outbound Analytics**: Track clicks from Pinterest to store
4. **ML-Based Selection**: Prioritize high-performing products
5. **Board Analytics**: Adjust board selection based on engagement
6. **Bulk Import**: Pin old products in batch mode
7. **Competitor Monitoring**: Alert on competitor mentions
8. **Hashtag Trends**: Auto-adjust hashtags based on trending

## Security Notes

✅ **Safe**:
- Credentials in .env (git-ignored)
- No hardcoded secrets
- API keys from free services (limited damage if exposed)
- HTTPS for all API calls

⚠️ **Be Careful**:
- Don't commit .env file
- Don't share `posting_history.json` (contains product IDs)
- Rotate Pinterest password if accidentally exposed
- Use app-specific password for Pinterest if available

🔐 **GitHub Actions Secrets**:
- All .env vars stored as encrypted secrets
- Only accessible during workflow runs
- Not logged in plaintext

---

**Version**: 1.0.0
**Last Updated**: 2026-05-12
**Maintainer**: MeeeShop automation team
