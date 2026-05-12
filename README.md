# MeeeShop Pinterest Automation 📌

Automate posting Shopify products to Pinterest with AI-powered content generation. Posts daily to relevant boards while following Pinterest's safety guidelines to avoid blocks.

## Features

✅ **No API Required** — Uses browser automation (Selenium) for 100% compatibility
✅ **AI-Powered Content** — Generates titles, descriptions, hashtags using free AI models (Gemini, Groq, OpenRouter)
✅ **Smart Board Routing** — Auto-routes products to relevant boards based on type/tags
✅ **Anti-Block Protection** — Daily limits, board rotation, posting cooldown to stay safe
✅ **Video Support** — Can use videos from meeeshop-youtube repository
✅ **GitHub Actions** — Daily automated posting on schedule
✅ **Posting History** — Tracks what's been posted to avoid duplicates

## Prerequisites

- **Pinterest Account** (with boards set up)
- **Shopify Store** (with API token)
- **Chrome Browser** (installed on system)
- **Python 3.10+**
- **At least one AI API key** (free options available):
  - Google Gemini (1M tokens/day free)
  - Groq (500K tokens/day free)
  - OpenRouter (24+ free models)

## Quick Start

### 1. Clone & Setup

```bash
cd c:\Users\USER\Downloads\Shopify_Claude
cd meeeshop-pinterest
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Configure Credentials

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Required:**
- `PINTEREST_EMAIL` — Your Pinterest login
- `PINTEREST_PASSWORD` — Your Pinterest password
- `SHOPIFY_STORE_URL` — e.g., `https://meeeshop.myshopify.com`
- `SHOPIFY_ACCESS_TOKEN` — From Shopify admin

**AI Keys (pick at least one):**
- `GEMINI_API_KEY` — https://aistudio.google.com (free, 1M tokens/day)
- `GROQ_API_KEY` — https://console.groq.com (free, 500K tokens/day)
- `OPENROUTER_API_KEY` — https://openrouter.ai (free, 24+ models)

### 3. Test Setup

```bash
# Test AI providers
python ai_client.py

# Test Shopify connection
python shopify_products.py

# Test content generator
python content_generator.py

# Test Pinterest client (manual)
python pinterest_client.py
```

### 4. Run Daily Posting

```bash
python pinterest_daily.py
```

This will:
1. Login to Pinterest
2. Fetch your boards
3. Pick a random product from Shopify
4. Generate AI-powered content (title, description, hashtags)
5. Post to relevant board
6. Update posting history

## Configuration

### Posting Limits (Anti-Block)

Edit `pinterest_daily.py`:

```python
MAX_PINS_PER_DAY = 3              # Max 3 pins/day (safe)
COOLDOWN_HOURS = 2                # Wait 2h between posts
BOARD_ROTATION_COOLDOWN = 24      # Don't post same board twice in 24h
```

**Pinterest Safety Guidelines:**
- ✅ 3-5 pins per day is safe
- ✅ Mix pins across different boards
- ⚠️ Posting >10/day risks temporary block
- ⚠️ Posting same pin to multiple boards is flagged
- ✅ Varied posting times help

### Board Mapping

In `shopify_products.py`, edit `get_pinterest_board_mapping()`:

```python
{
    "Dresses & Gowns": ["dress", "gown", "maxi"],
    "Tops & Shirts": ["shirt", "top", "blouse"],
    "Pants & Jeans": ["pants", "jeans", "trousers"],
    # Add your boards here
}
```

Products are routed to boards matching their type/tags.

## GitHub Actions Setup

### 1. Add Secrets

In GitHub repo settings → Secrets → New secret, add:

```
PINTEREST_EMAIL
PINTEREST_PASSWORD
SHOPIFY_STORE_URL
SHOPIFY_ACCESS_TOKEN
STORE_BASE_URL
GEMINI_API_KEY (or GROQ_API_KEY or OPENROUTER_API_KEY)
```

### 2. Enable Actions

- Go to repo → Actions → Enable GitHub Actions
- Workflows auto-run daily at **2 PM UTC** (10 AM EST)
- Manually trigger: Actions → Daily Pinterest Posting → Run workflow

## Monitoring

### Posting History

View `posting_history.json`:

```json
{
  "posts": [
    {
      "product_id": "123456789",
      "title": "Vintage High-Waisted Jeans",
      "board": "Pants & Jeans",
      "timestamp": "2026-05-12T14:30:00"
    }
  ],
  "board_last_used": {
    "Pants & Jeans": "2026-05-12T14:30:00"
  },
  "daily_count": 2,
  "last_post_time": "2026-05-12T14:30:00"
}
```

### Logs

GitHub Actions logs are available at:
`https://github.com/meeeshop/meeeshop-pinterest/actions`

## Troubleshooting

### Pinterest Login Fails

- [ ] Email/password correct?
- [ ] Two-factor enabled? Disable or use app password
- [ ] Account flagged? Try logging in manually first
- [ ] ChromeDriver outdated? Run: `pip install --upgrade webdriver-manager`

### Content Generation Fails

- [ ] At least one AI key set in `.env`?
- [ ] Check API key limits (Gemini: 1M tokens/day)
- [ ] Try different provider in fallback order: Gemini → Groq → OpenRouter

### Posting to Pinterest Fails

- [ ] Board name exact match? Check `pinterest_fetch_boards()` output
- [ ] Image URL accessible? Check `image_url` in product data
- [ ] Already posted? Check `posting_history.json`
- [ ] Browser version? Update Chrome: `pip install --upgrade webdriver-manager`

### Daily Limit Reached

- Check `posting_history.json` — daily_count shows posts today
- Limit resets at midnight UTC
- Increase `MAX_PINS_PER_DAY` carefully (3-5 is safe)

## AI Models Priority

### Best for Content Generation (SEO):
1. **Minimax M2.5** — SOTA content, perfect for Pinterest
2. **Gemini 2.0 Flash** — Fast, reliable, free
3. **Groq Llama-3.3-70B** — High quality, reasonable latency

### Used if Primary Fails:
4. Qwen 3 Coder 480B (excellent multimodal)
5. Meta Llama 3.3 70B (good generalist)
6. Hermes 3 405B (agentic, creative)

All fallbacks happen automatically with transparent logging.

## Video Integration

To post YouTube videos:

1. Ensure `meeeshop-youtube` repo is in parent directory
2. Script looks for videos in:
   - `meeeshop-youtube/videos/`
   - `meeeshop-youtube/output/`
   - `meeeshop-youtube/shorts/`
3. Randomly selects a video if available

Edit `pinterest_daily.py` → `get_video_from_youtube_repo()` to customize.

## Keyword Strategy

Content generator uses AI to produce:
- **Titles**: Engagement keywords + power words (Stunning, Chic, Versatile)
- **Descriptions**: Lifestyle benefits + search keywords + CTAs
- **Hashtags**: Style, occasion, demographic, trend tags
- **Keywords**: Long-tail phrases for SEO

All optimized for **women shoppers in USA** (primary audience).

## Pinterest Guidelines for Women Fashion

✅ **Do:**
- Post 3-5 quality pins/day max
- Mix product pins with lifestyle/inspiration
- Include benefit-focused descriptions
- Use relevant hashtags (10-15)
- Link to product pages
- Vary posting times
- Rotate across boards

❌ **Don't:**
- Post same pin >1x/day or to multiple boards
- Use manipulative click-bait titles
- Include irrelevant links (external shopping links)
- Post low-quality/stretched images
- Spam same hashtags repeatedly
- Post >10 pins/day

## Performance Targets

Goal: **30-40% CTR improvement** with organic reach to women shoppers

Tracking metrics in GitHub Actions logs:
- Pins posted per day
- Boards utilized
- Product types featured
- Content performance

## Extending

### Add More Boards

Edit `shopify_products.py`:
```python
{
    "New Board Name": ["keyword1", "keyword2"],
}
```

### Custom Content Rules

Edit `content_generator.py`:
- `generate_pinterest_title()` — customize title logic
- `generate_hashtags()` — add more hashtag sources
- `generate_keywords_for_seo()` — enhance SEO keywords

### Use Different AI Models

Edit `ai_client.py`:
- Change `_PROVIDERS` order
- Add new provider (OpenAI, Claude, etc.)
- Adjust temperature/max_tokens for different content types

## Support

For issues:
1. Check logs: `Pinterest_daily.log`
2. Review `posting_history.json`
3. Test components individually: `ai_client.py`, `shopify_products.py`, `pinterest_client.py`
4. Check GitHub Actions runs for detailed error output

## License

MIT — Free to use and modify for your store.

## Next Steps

1. ✅ Setup `.env` with credentials
2. ✅ Test all components (`python ai_client.py`, etc.)
3. ✅ Configure board mapping
4. ✅ Run manual test: `python pinterest_daily.py`
5. ✅ Push to GitHub
6. ✅ Add secrets to GitHub
7. ✅ Enable GitHub Actions
8. ✅ Monitor first week of automated posting
9. ✅ Adjust `MAX_PINS_PER_DAY` based on performance

---

**Created**: 2026-05-12
**Python**: 3.10+
**Maintenance**: Minimal (update ChromeDriver if browser updates)
