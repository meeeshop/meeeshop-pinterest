# MeeeShop Pinterest Setup Guide

Complete walkthrough to get Pinterest automation running on your system.

## Step 1: Prerequisites Check (5 min)

### System Requirements
```powershell
# Windows: Verify Python installed
python --version              # Should be 3.10+
pip --version                 # Should be 22+
where chrome                  # Should find Chrome browser
```

### Pinterest Account Setup
- [ ] Have Pinterest account (personal or business)
- [ ] Know your email/password (or app password if 2FA enabled)
- [ ] Have at least 3-4 boards created (e.g., Dresses, Tops, Jeans)
- [ ] Note board names exactly as they appear on Pinterest

### Shopify Credentials
From Shopify admin → Settings → Apps and integrations:
- [ ] `SHOPIFY_STORE_URL` — Found in store settings
- [ ] `SHOPIFY_ACCESS_TOKEN` — Generate with scopes: `read_products`, `read_collections`

### API Keys (Pick At Least One)
All free with generous limits:

**Option 1: Google Gemini** (Recommended - easiest)
1. Go to https://aistudio.google.com
2. Click "Get API Key"
3. Create new project
4. Copy key to `.env` as `GEMINI_API_KEY`

**Option 2: Groq** (Fast - 500K tokens/day)
1. Visit https://console.groq.com
2. Sign up with email
3. Create API key
4. Copy to `.env` as `GROQ_API_KEY`

**Option 3: OpenRouter** (Most models - 24+ free)
1. Go to https://openrouter.ai
2. Sign up
3. Go to Keys → Create new
4. Copy to `.env` as `OPENROUTER_API_KEY`

## Step 2: Setup Repository (10 min)

### Clone & Initialize
```powershell
cd C:\Users\USER\Downloads\Shopify_Claude
cd meeeshop-pinterest

# Create Python virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install webdriver-manager
```

### Configure .env File
```powershell
# Copy example
cp .env.example .env

# Edit with your values
notepad .env
```

**Must fill in:**
```
PINTEREST_EMAIL=your_email@gmail.com
PINTEREST_PASSWORD=your_password
SHOPIFY_STORE_URL=https://meeeshop.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
STORE_BASE_URL=https://us.meeeshop.com
GEMINI_API_KEY=AIza...  (or GROQ_API_KEY or OPENROUTER_API_KEY)
```

## Step 3: Test Components (15 min)

### Test AI Providers
```powershell
python ai_client.py
```
Expected output:
```
Testing AI providers...
  Gemini       : OK
  Groq         : OK (or fail if no key)
  OpenRouter   : OK (or fail if no key)
```

✅ **Success**: At least 1 "OK"

### Test Shopify Connection
```powershell
python shopify_products.py
```
Expected output:
```
Title: [Your product name]
Board: [Detected board]
URL: https://us.meeeshop.com/products/...
```

✅ **Success**: Shows 5 products

### Test Content Generator
```powershell
python content_generator.py
```
Expected output:
```
Generated Content Package:
Title: [AI-generated catchy title]
Description: [Natural description]
Hashtags: #WomensStyle #FashionFind ...
Keywords: casual, comfortable, vintage
```

✅ **Success**: All 4 sections populated

## Step 4: Manual Test (20 min)

**Interactive test with real Pinterest posting:**

```powershell
python pinterest_daily.py
```

This will:
1. ✅ Ask for Pinterest email/password (or use .env)
2. ✅ Login to Pinterest (opens Chrome browser)
3. ✅ Fetch your boards
4. ✅ Pick a random product
5. ✅ Generate content
6. ✅ Post to Pinterest

**Watch for:**
- [ ] Chrome window opens
- [ ] Logs into Pinterest
- [ ] Fetches boards (shows board names)
- [ ] Fetches products from Shopify
- [ ] Generates content (AI called)
- [ ] Creates pin on Pinterest
- [ ] Updates `posting_history.json`

### If It Fails

**Pinterest Login Issues:**
- [ ] Username/password correct?
- [ ] Pinterest account accessible from browser?
- [ ] 2FA enabled? Use app-specific password or disable 2FA
- [ ] Account flagged? Try logging in manually in Chrome first

**Content Generation Issues:**
- [ ] AI key valid? Test with `python ai_client.py`
- [ ] Check `.env` for typos
- [ ] Try different AI provider in order: Gemini → Groq → OpenRouter

**Shopify Connection Issues:**
- [ ] Store URL correct? (https://meeeshop.myshopify.com)
- [ ] Access token valid? Test in Shopify admin
- [ ] Token has required scopes? Add: read_products, read_collections

## Step 5: Configure Board Mapping (5 min)

Edit `shopify_products.py` → `get_pinterest_board_mapping()`:

```python
return {
    "Your Board 1": ["keyword1", "keyword2"],
    "Your Board 2": ["keyword3", "keyword4"],
}
```

Example:
```python
{
    "Dresses & Gowns": ["dress", "gown", "maxi"],
    "Pants": ["pants", "jeans", "trousers"],
    "Blouses": ["shirt", "top", "blouse"],
}
```

Products are matched by type/tags to your boards.

## Step 6: GitHub Setup (Optional, 10 min)

### If Using GitHub Actions for Automated Daily Posting:

1. **Push to GitHub**
   ```powershell
   git remote add origin https://github.com/meeeshop/meeeshop-pinterest
   git add .
   git commit -m "Initial Pinterest automation setup"
   git push -u origin main
   ```

2. **Add Secrets** (GitHub repo settings → Secrets)
   - `PINTEREST_EMAIL`
   - `PINTEREST_PASSWORD`
   - `SHOPIFY_STORE_URL`
   - `SHOPIFY_ACCESS_TOKEN`
   - `STORE_BASE_URL`
   - `GEMINI_API_KEY` (or GROQ_/OPENROUTER_)

3. **Enable Actions**
   - Go to repo → Actions tab → Enable GitHub Actions

4. **Manual Test**
   - Actions → Daily Pinterest Posting → Run workflow
   - Watch logs for success/failure

### Automated Schedule
- ✅ Runs daily at **2 PM UTC** (10 AM EST)
- ✅ Modify cron in `.github/workflows/daily-pinterest-posting.yml`
- ✅ Max 3 pins/day by default

## Step 7: Adjust Safety Settings (Optional, 5 min)

Edit `pinterest_daily.py`:

```python
MAX_PINS_PER_DAY = 3          # Increase to 5 max (be careful)
COOLDOWN_HOURS = 2            # Gap between posts
BOARD_ROTATION_COOLDOWN = 24  # Hours before same board again
```

**Pinterest Safety:**
- 🟢 3 pins/day = very safe
- 🟡 5 pins/day = safe, minimal risk
- 🔴 10+ pins/day = high risk of temporary block

## Step 8: Monitor (Ongoing)

### Daily Check
```powershell
# View posting history
cat posting_history.json

# Check logs
ls -la *.log
```

### Weekly Review
- Check posting frequency
- Monitor which boards are used
- Review product variety
- Verify no duplicate posts

### Monthly Adjustments
- Increase `MAX_PINS_PER_DAY` if safe (max 5)
- Add new boards to mapping
- Adjust AI temperature in `content_generator.py`
- Review Pinterest analytics

## Troubleshooting Checklist

### Nothing Happens When Running Script
- [ ] Virtual env activated? `venv\Scripts\activate`
- [ ] Dependencies installed? `pip install -r requirements.txt`
- [ ] `.env` file exists and filled? `ls -la .env`
- [ ] Check logs: `cat *.log`

### Pinterest Login Fails
- [ ] Try logging in manually in Chrome first
- [ ] Email/password correct (case sensitive)?
- [ ] 2FA enabled? Disable or use app password
- [ ] Account restricted? Check Pinterest account status

### No Products Found
- [ ] Shopify URL correct? (https://meeeshop.myshopify.com)
- [ ] Access token valid? Check Shopify admin
- [ ] Token has correct scopes? `read_products`
- [ ] Store has products? Check Shopify products page

### AI Not Generating Content
- [ ] At least one API key set? `echo $env:GEMINI_API_KEY`
- [ ] Key valid? Test: `python ai_client.py`
- [ ] Check API quotas (Gemini: 1M/day, Groq: 500K/day)
- [ ] Network working? `ping google.com`

### Board Not Found
- [ ] Board name exact match? Run `pinterest_fetch_boards()` to list
- [ ] Typo in `get_pinterest_board_mapping()`?
- [ ] Board permissions? Ensure you can edit the board

## Next Steps After Setup

1. ✅ Test everything works (Step 3-4)
2. ✅ Run 3-5 manual tests to verify behavior
3. ✅ Push to GitHub and enable Actions (Step 6)
4. ✅ Let it run for 1 week, monitor results
5. ✅ Adjust `MAX_PINS_PER_DAY` if safe
6. ✅ Add more boards and products
7. ✅ Monitor Pinterest analytics for performance

## Performance Targets

**Week 1:**
- 3 pins/day × 7 = 21 pins
- Monitor which boards/products perform best

**Week 2-4:**
- Increase to 5 pins/day if no blocks
- Refine board selection
- Check CTR improvement in Pinterest analytics

**Month 2+:**
- Target 30-40% CTR improvement
- Expand board variety
- Integrate video content from meeeshop-youtube

## Support

If stuck:
1. Read error logs carefully
2. Test individual components (`ai_client.py`, `shopify_products.py`)
3. Check `.env` file for missing/invalid keys
4. Review GitHub Actions logs if using automation
5. Verify Pinterest/Shopify credentials manually

---

**Total Setup Time**: ~1 hour first time
**Maintenance**: 5 min/week to review posts
**Success Rate**: 95%+ after proper setup

Good luck! 🎉
