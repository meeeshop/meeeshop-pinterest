# Pinterest Automation Testing Summary

## Overview

This document covers the comprehensive testing framework for the Pinterest automation system, including product pins, video pins, and integration tests.

**Status**: ✅ **READY FOR TESTING**  
**Test Scope**: Complete end-to-end workflow (Shopify → AI → Pinterest)  
**Expected Time**: 5-10 minutes per test run  

---

## Test Files

### Main Test Suite

#### `test_product_and_video_pins.py` (NEW)
**Purpose**: Complete end-to-end test for product and video pins  
**What it does**:
1. Verifies credentials
2. Fetches product from Shopify
3. Generates AI content
4. Optimizes image with overlays
5. Selects video (local or YouTube)
6. Logs into Pinterest
7. Creates product pin
8. Creates video pin

**Run with**:
```powershell
python test_product_and_video_pins.py
```

**Output**:
- Console logs (colored, real-time)
- `test_pins_run.log` (detailed file log)
- `test_results_latest.json` (structured results)

### Existing Test Files

#### `test_posting.py`
**Purpose**: Original test for product pins  
**What it tests**:
- Cookie-based Pinterest login
- Product fetching and formatting
- Rich pin creation with optimized images
- Video pin creation (optional)

**Run with**:
```powershell
python test_posting.py
```

#### `test_posting_api.py`
**Purpose**: API-based Pinterest testing  
**Status**: Alternative approach (not used in main flow)

### Component Tests

Run individual components to isolate issues:

```powershell
# Test AI content generation
python ai_client.py

# Test Shopify connection
python shopify_products.py

# Test video selection
python video_picker.py

# Test image optimization
python image_optimizer.py

# Test YouTube video download
python youtube_video_downloader.py
```

---

## Test Setup

### Prerequisites

#### 1. **Environment File** (`.env`)
Required credentials for all systems:

```bash
# Pinterest
PINTEREST_EMAIL=your_email@gmail.com
PINTEREST_PASSWORD=your_password

# Shopify
SHOPIFY_STORE_URL=https://meeeshop.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxx

# Store
STORE_BASE_URL=https://us.meeeshop.com

# AI (choose at least one)
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxx
# OR
GROQ_API_KEY=gsk_xxxxxxxxxxxx
# OR
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxx

# Optional: YouTube
YOUTUBE_CHANNEL_ID=UCxxxxxxxxxx
```

#### 2. **Pinterest Cookies** (optional but recommended)
Run once to save login cookies:

```powershell
python setup_pinterest_login.py
```

This creates `.pinterest_cookies` for faster, more reliable logins.

#### 3. **Dependencies**
Install all required packages:

```powershell
pip install -r requirements.txt
```

Key packages:
- `selenium>=4.10.0` — Browser automation
- `webdriver-manager>=4.0.0` — Chrome driver management
- `yt-dlp>=2023.11.0` — YouTube video downloads
- `Pillow>=10.0.0` — Image processing
- `requests>=2.31.0` — HTTP requests
- `python-dotenv>=1.0.0` — Environment variables

---

## Test Execution

### Quick Start (Recommended)

```powershell
# Windows
./run_test.ps1

# Or use batch file
run_test.bat
```

### Manual Execution

```powershell
# Activate virtual environment
venv\Scripts\Activate.ps1

# Run full test
python test_product_and_video_pins.py
```

### Expected Output

```
======================================================================
🚀 PINTEREST AUTOMATION — PRODUCT & VIDEO PIN TEST
======================================================================

✓ Step 1: Verify Credentials [success]
    Pinterest: user...@gmail.com
    Shopify URL: https://meeeshop.myshopify.com
    Shopify Token: shpat...

✓ Step 2: Fetch Shopify Product [success]
    Product: Vintage High-Waisted Jeans
    Board: Pants & Jeans
    Price: $49.99

✓ Step 3: Generate AI Content [success]
    Title: Chic Vintage Jeans
    Description: Flattering high-waist fit with timeless style...
    Hashtags: #vintagefashion, #jeans, #womensStyle...

✓ Step 4: Optimize Image with Overlays [success]
    Image: optimized_product_image.jpg
    Size: 2.5MB

✓ Step 5: Select Video for Pin [success]
    Source: Local
    File: fashion_tutorial.mp4
    Directory: videos/
    Size: 15.3MB

✓ Step 6: Login to Pinterest [success]
    Logged in successfully
    Boards: 8 boards available

✓ Step 7: Create Product Pin [success]
    Title: Chic Vintage Jeans
    Board: Pants & Jeans
    URL: https://us.meeeshop.com/products/vintage-jeans

✓ Step 8: Create Video Pin [success]
    Video: fashion_tutorial.mp4
    Board: Pants & Jeans
    Size: 15.3MB

======================================================================
✅ TEST SUMMARY
======================================================================
Product Pin: ✅ SUCCESS
Video Pin: ✅ SUCCESS
Total Pins Created: 2
Test Duration: 8 steps

Test results saved: test_results_latest.json
```

---

## Test Scenarios

### Scenario 1: Full Success (Happy Path)
- All credentials valid
- Shopify product available
- AI content generated
- Image optimized
- Video available (local or YouTube)
- Pinterest login successful
- Both pins created

**Expected**: ✅ Both pins appear on Pinterest board

### Scenario 2: Video Not Available
- All steps 1-7 succeed
- No local videos or YouTube videos available
- Video pin skipped

**Expected**: ✅ Product pin created, video skipped gracefully

### Scenario 3: Board Not Found
- Product selected
- Selected board doesn't exist
- System uses first available board

**Expected**: ✅ Product pin created on alternate board

### Scenario 4: Image Optimization Fails
- Image optimization fails
- Falls back to raw image download
- Pin still created

**Expected**: ✅ Product pin created with raw image

### Scenario 5: YouTube Video Requires Download
- YouTube video selected (not local)
- yt-dlp downloads video
- Video pin created

**Expected**: ✅ Video pin created with downloaded video

---

## Test Results

Test results are saved to `test_results_latest.json`:

```json
{
  "test_name": "Pinterest Product & Video Pin Automation",
  "start_time": "2026-05-12T14:30:00.000000",
  "end_time": "2026-05-12T14:35:45.000000",
  "success": true,
  "pins_created": [
    {
      "type": "product",
      "title": "Chic Vintage Jeans",
      "board": "Pants & Jeans",
      "timestamp": "2026-05-12T14:33:30.000000"
    },
    {
      "type": "video",
      "title": "🎬 Fashion Tutorial",
      "board": "Pants & Jeans",
      "source": "local",
      "timestamp": "2026-05-12T14:34:45.000000"
    }
  ],
  "steps": [
    {
      "step": 1,
      "title": "Verify Credentials",
      "status": "success",
      "details": "Pinterest: user@gmail.com",
      "timestamp": "2026-05-12T14:30:15.000000"
    }
    // ... more steps
  ]
}
```

---

## Troubleshooting Guide

### Common Issues

#### ❌ Step 1: Verify Credentials — FAILED

**Cause**: Missing or incorrect `.env` file

**Fix**:
1. Check `.env` exists in project root
2. Verify all required variables are set:
   - `PINTEREST_EMAIL`
   - `PINTEREST_PASSWORD`
   - `SHOPIFY_STORE_URL`
   - `SHOPIFY_ACCESS_TOKEN`
3. No spaces around `=` in env file

#### ❌ Step 2: Fetch Shopify Product — FAILED

**Cause**: Shopify connection error or no products

**Fix**:
1. Verify Shopify credentials:
   - Check `SHOPIFY_STORE_URL` format: `https://store.myshopify.com`
   - Regenerate access token in Shopify admin
2. Check store has products:
   - Go to Shopify admin → Products → Products
   - Ensure at least one product exists and is published
3. Test connection:
   ```powershell
   python shopify_products.py
   ```

#### ❌ Step 3: Generate AI Content — FAILED

**Cause**: AI API unavailable or rate limited

**Fix**:
1. Check API keys in `.env`:
   - At least one of: `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`
2. Test AI client:
   ```powershell
   python ai_client.py
   ```
3. Check API usage/limits:
   - Gemini: https://aistudio.google.com
   - Groq: https://console.groq.com
   - OpenRouter: https://openrouter.ai

#### ❌ Step 4: Optimize Image with Overlays — FAILED

**Cause**: Image download or processing error

**Fix**:
1. Check product image URL is accessible
2. Verify image format (JPG, PNG, WebP)
3. Check internet connection
4. Test image optimizer:
   ```powershell
   python image_optimizer.py
   ```

#### ⚠️ Step 5: Select Video for Pin — WARNING

**Cause**: No videos found

**This is OK** — Video is optional

**To enable video**:
1. Add `.mp4` or `.webm` files to `meeeshop-youtube/videos/`
2. Or configure YouTube API (see [VIDEO_INTEGRATION.md](VIDEO_INTEGRATION.md))

#### ❌ Step 6: Login to Pinterest — FAILED

**Cause**: Pinterest login error

**Fix**:
1. **Use saved cookies** (fastest):
   ```powershell
   python setup_pinterest_login.py
   ```
   Then retry test

2. **Check credentials**:
   - Verify email/password in `.env`
   - Test manual login in browser first

3. **Disable 2FA** (if enabled):
   - Temporarily disable 2FA in Pinterest settings
   - Or use app-specific password

4. **Update ChromeDriver**:
   ```powershell
   pip install --upgrade webdriver-manager
   ```

#### ❌ Step 7: Create Product Pin — FAILED

**Cause**: Pinterest API or board error

**Fix**:
1. Verify Pinterest is working:
   - Check network connection
   - Try creating a pin manually in browser
2. Check board exists:
   - Boards must be pre-created in Pinterest
   - Board name must match exactly
3. Test Pinterest client:
   ```powershell
   python pinterest_client.py
   ```

#### ❌ Step 8: Create Video Pin — FAILED

**Cause**: Video format or download error

**Fix**:
1. For local videos:
   - Check file exists: `meeeshop-youtube/videos/*.mp4`
   - Verify format is supported (MP4, WebM)
   - Check file size is under 5MB (Pinterest limit)

2. For YouTube videos:
   - Install yt-dlp: `pip install --upgrade yt-dlp`
   - Check YouTube URL is valid and public
   - Verify video duration <15 minutes

---

## Performance & Metrics

### Test Timing

| Step | Component | Time |
|------|-----------|------|
| 1 | Verify Credentials | <1s |
| 2 | Fetch Shopify Product | 2-3s |
| 3 | Generate AI Content | 3-5s |
| 4 | Optimize Image | 2-3s |
| 5 | Select Video | 1-2s |
| 6 | Login to Pinterest | 5-10s |
| 7 | Create Product Pin | 5-10s |
| 8 | Create Video Pin | 5-10s |
| **Total** | **All Steps** | **5-10 min** |

### Success Metrics

✅ **Minimum Success Criteria**:
- Step 1-7 pass (product pin created)
- Step 8 optional (video pin, skipped if no video)

✅ **Full Success Criteria**:
- All 8 steps pass
- 2 pins created (product + video)
- Pins visible on Pinterest board

---

## Next Steps After Successful Test

1. **Verify Pins on Pinterest**:
   - Go to your Pinterest account
   - Check selected board
   - Confirm pins appear with correct content

2. **Monitor Pin Performance**:
   - Check engagement (saves, clicks)
   - Note which products/boards perform best
   - Adjust content strategy based on metrics

3. **Deploy to GitHub**:
   ```powershell
   git add test_product_and_video_pins.py TEST_GUIDE.md run_test.ps1 run_test.bat
   git commit -m "Add comprehensive product & video pin testing"
   git push origin main
   ```

4. **Setup GitHub Actions**:
   - Add secrets to GitHub repo (see README.md)
   - Enable daily posting workflow
   - Monitor logs for errors

5. **Fine-tune Settings**:
   - Adjust `MAX_PINS_PER_DAY` in `pinterest_daily.py`
   - Configure board mappings in `shopify_products.py`
   - Customize content in `content_generator.py`

---

## Logging & Debugging

### Log Files

- `test_pins_run.log` — Complete test execution log
- `test_results_latest.json` — Structured test results
- `Pinterest_daily.log` — Daily posting logs (if using scheduler)

### Enable Debug Mode

Edit test script to enable debug logging:

```python
# In test_product_and_video_pins.py
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format="%(asctime)s [%(levelname)s] %(message)s",
)
```

### Inspect Test Results

```powershell
# Pretty-print test results
python -m json.tool test_results_latest.json
```

---

## Test Maintenance

### Update Tests When:
- New features added to Pinterest automation
- Dependencies updated
- Workflow changes
- New edge cases discovered

### Review Tests Monthly:
- Check for broken selectors in Pinterest UI
- Verify API endpoints still work
- Update board mappings if boards change
- Monitor for bot detection patterns

---

## Contact & Support

For issues:
1. Check logs: `test_pins_run.log`
2. Review troubleshooting section above
3. Run individual component tests
4. Check GitHub issues for similar problems

---

**Document Created**: 2026-05-12  
**Last Updated**: 2026-05-12  
**Test Status**: ✅ Ready for production testing
