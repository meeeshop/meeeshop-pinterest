# Pre-Test Checklist ✅

Before running `test_product_and_video_pins.py`, verify these items:

## Credentials & Setup (5 min)

### Pinterest
- [ ] Pinterest account created
- [ ] At least 1 board created (e.g., "Fashion", "Dresses")
- [ ] Account is active (no blocks or restrictions)
- [ ] 2FA disabled OR app password generated
- [ ] Email and password noted correctly in `.env`

### Shopify Store
- [ ] Shopify store accessible (URL format: `https://store.myshopify.com`)
- [ ] Access token generated in Shopify admin:
  - Go to: Settings → Apps and integrations → Develop apps → Create
  - Add required scopes: `read_products`, `read_orders`
  - Install and copy access token
- [ ] At least 5 products published in store
  - Each product should have:
    - Title
    - Description
    - Product type
    - Tags
    - Product image (URL)
    - Price

### Environment File (`.env`)
Create file in root directory with:

```
PINTEREST_EMAIL=your_email@gmail.com
PINTEREST_PASSWORD=your_password
SHOPIFY_STORE_URL=https://store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxx
STORE_BASE_URL=https://us.meeeshop.com
```

#### AI API Key (pick at least ONE):

**Option 1: Google Gemini** (Easiest, Free)
- [ ] Go to: https://aistudio.google.com
- [ ] Click "Get API Key" button
- [ ] Create new API key
- [ ] Copy to `.env`: `GEMINI_API_KEY=AIza...`

**Option 2: Groq** (Fast, Free)
- [ ] Go to: https://console.groq.com
- [ ] Sign up or login
- [ ] Create API key
- [ ] Copy to `.env`: `GROQ_API_KEY=gsk_...`

**Option 3: OpenRouter** (Multiple models, Free)
- [ ] Go to: https://openrouter.ai
- [ ] Sign up or login
- [ ] Create API key
- [ ] Copy to `.env`: `OPENROUTER_API_KEY=sk-or-...`

### Test `.env` File

```powershell
# Verify .env is readable
type .env

# Should output:
PINTEREST_EMAIL=...
PINTEREST_PASSWORD=...
SHOPIFY_STORE_URL=...
etc.
```

## System & Dependencies (5 min)

### Software
- [ ] Python 3.10+ installed
  ```powershell
  python --version  # Should be 3.10 or higher
  ```
- [ ] Chrome browser installed (required for Selenium)
  ```powershell
  # Windows Start Menu → Google Chrome
  ```
- [ ] Git installed (for version control)
  ```powershell
  git --version
  ```

### Python Dependencies
- [ ] Virtual environment created
  ```powershell
  python -m venv venv
  ```
- [ ] Virtual environment activated
  ```powershell
  venv\Scripts\Activate.ps1
  ```
- [ ] Requirements installed
  ```powershell
  pip install -r requirements.txt
  # Should show: Successfully installed selenium webdriver-manager yt-dlp ...
  ```

### Verify Installation
```powershell
# Test each module
python -c "import selenium; print('✓ Selenium OK')"
python -c "import requests; print('✓ Requests OK')"
python -c "import PIL; print('✓ Pillow OK')"
python -c "import dotenv; print('✓ python-dotenv OK')"
```

## Optional: Video Setup (3 min)

### For Local Videos
- [ ] Folder structure created: `meeeshop-youtube/videos/`
- [ ] Sample video files added (`.mp4` or `.webm`)
  - Recommended: 5-15 seconds
  - Size: <50MB
  - Format: MP4 or WebM

### For YouTube Videos (Optional)
If you want to auto-download videos from YouTube:
- [ ] YouTube API credentials obtained (see [VIDEO_INTEGRATION.md](VIDEO_INTEGRATION.md))
- [ ] OAuth token configured in `.env`
- [ ] OR rely on local videos (simpler)

## Optional: Pinterest Cookies (2 min)

For faster, more reliable login:

```powershell
# Run cookie setup script
python setup_pinterest_login.py
```

This creates `.pinterest_cookies` file.
- [ ] `setup_pinterest_login.py` script completed
- [ ] `.pinterest_cookies` file exists
- [ ] Cookie file is <1MB

## Pre-Test Validation (3 min)

### Test Individual Components
Before running full test, validate each component:

```powershell
# 1. Test AI provider
python ai_client.py
# Should output: "✓ AI provider OK"

# 2. Test Shopify connection
python shopify_products.py
# Should list 5+ products

# 3. Test video selection
python video_picker.py
# Should find videos (or say "No videos found" - OK)

# 4. Test image optimizer
python image_optimizer.py
# Should download and process sample image
```

**All component tests pass? ✓ Ready to run full test!**

## Run the Full Test (5-10 min)

### Option 1: Using PowerShell (Recommended)
```powershell
./run_test.ps1
```

### Option 2: Using Batch File
```powershell
run_test.bat
```

### Option 3: Manual
```powershell
venv\Scripts\Activate.ps1
python test_product_and_video_pins.py
```

## After Test Completes

### Check Results
- [ ] Console shows "✅ TEST PASSED" or "❌ TEST FAILED"
- [ ] Log file exists: `test_pins_run.log`
- [ ] Results file exists: `test_results_latest.json`

### If PASSED ✅
1. [ ] Check your Pinterest board
   - Go to: https://pinterest.com/me/boards/
   - Select board
   - Verify pins appear with correct content
2. [ ] Review pin quality
   - Image looks good
   - Title and description are relevant
   - Link to product works
3. [ ] Proceed to next steps:
   - Push to GitHub
   - Setup GitHub Actions
   - Enable daily posting

### If FAILED ❌
1. [ ] Check log file: `test_pins_run.log`
   - Find which step failed
   - Read error message
2. [ ] Review troubleshooting section in [TEST_GUIDE.md](TEST_GUIDE.md)
3. [ ] Run individual component test
   - Isolate the failing component
   - Fix and retry
4. [ ] Contact support if needed

## Troubleshooting Quick Reference

| Issue | Fix |
|-------|-----|
| Python not found | Download from python.org |
| Import error (selenium, etc.) | Run: `pip install -r requirements.txt` |
| API key invalid | Test with: `python ai_client.py` |
| Shopify connection fails | Check credentials and token scope |
| Pinterest login fails | Run: `python setup_pinterest_login.py` |
| No boards found | Create board in Pinterest first |
| ChromeDriver issues | Run: `pip install --upgrade webdriver-manager` |
| Image optimization fails | Check internet connection |
| Video download fails | Ensure yt-dlp installed: `pip install --upgrade yt-dlp` |

## Estimated Timeline

```
Setup & Verification: 10 min
  • Credentials: 5 min
  • Dependencies: 5 min

Component Tests: 5 min
  • AI provider: 1 min
  • Shopify: 1 min
  • Video: 1 min
  • Image: 1 min
  • Pinterest login: 1 min

Full Test Run: 5-10 min
  • Shopify fetch: 2-3s
  • AI content: 3-5s
  • Image optimize: 2-3s
  • Pinterest login: 5-10s
  • Create pins: 10-15s

Total: 20-25 minutes
```

## Success Criteria ✅

**Test is successful when:**
1. ✅ All credential checks pass
2. ✅ Shopify product fetched
3. ✅ AI content generated
4. ✅ Image optimized
5. ✅ Pinterest login successful
6. ✅ Product pin created on Pinterest board
7. ✅ Pins visible when you check Pinterest

**Video pin is optional:**
- ✅ If video available: created successfully
- ⚠️ If no video: skipped gracefully (NOT a failure)

---

## Checklist Summary

```
BEFORE TEST:
☐ Pinterest account with board ready
☐ Shopify store with 5+ products
☐ .env file with all credentials
☐ API key (Gemini/Groq/OpenRouter)
☐ Python 3.10+ installed
☐ Chrome browser installed
☐ Virtual environment created and activated
☐ Requirements installed (pip install -r requirements.txt)
☐ Component tests pass (ai_client.py, shopify_products.py, etc.)

DURING TEST:
☐ Console shows progress (8 steps)
☐ No errors or exceptions

AFTER TEST:
☐ Check: test_results_latest.json shows success: true
☐ Check: Pins appear on Pinterest board
☐ Review: Pin content and quality

READY TO PROCEED:
☐ YES → Push to GitHub and setup GitHub Actions
☐ NO → Review troubleshooting and retry
```

---

**Checklist Version**: 2026-05-12  
**Estimated Time**: 20-25 minutes  
**Status**: ✅ Ready to start
