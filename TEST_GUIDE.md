# Pinterest Automation Test Guide

## Quick Start — Test Product & Video Pins (10 min)

### Prerequisites Checklist
- [ ] `.env` file configured with all credentials
- [ ] Pinterest account with at least one board
- [ ] Shopify store with products
- [ ] Chrome browser installed
- [ ] Python 3.10+ with venv activated

### Run the Complete Test

```powershell
# Windows
python test_product_and_video_pins.py
```

This will:
1. ✅ Verify all credentials are set
2. 🛍️ Fetch a product from Shopify
3. 🤖 Generate AI content (title, description, hashtags)
4. 🎨 Optimize image with overlays
5. 🎬 Find & select video (local or YouTube)
6. 🔒 Login to Pinterest with saved cookies
7. 📌 Create **product pin** on selected board
8. 📹 Create **video pin** with product video

### Expected Output

```
70 PINTEREST AUTOMATION — PRODUCT & VIDEO PIN TEST
[INFO] ✓ Step 1: Verify Credentials [success]
[INFO] ✓ Step 2: Fetch Shopify Product [success]
[INFO] ✓ Step 3: Generate AI Content [success]
[INFO] ✓ Step 4: Optimize Image with Overlays [success]
[INFO] ✓ Step 5: Select Video for Pin [success]
[INFO] ✓ Step 6: Login to Pinterest [success]
[INFO] ✓ Step 7: Create Product Pin [success]
[INFO] ✓ Step 8: Create Video Pin [success]

====================================================================
✅ TEST SUMMARY
====================================================================
Product Pin: ✅ SUCCESS
Video Pin: ✅ SUCCESS
Total Pins Created: 2
Test Duration: 8 steps
```

### Test Results

Results are saved to `test_results_latest.json`:

```json
{
  "test_name": "Pinterest Product & Video Pin Automation",
  "start_time": "2026-05-12T14:30:00.000000",
  "success": true,
  "pins_created": [
    {
      "type": "product",
      "title": "Vintage High-Waisted Jeans",
      "board": "Pants & Jeans",
      "timestamp": "2026-05-12T14:30:45.000000"
    },
    {
      "type": "video",
      "title": "🎬 Fashion Styling Tutorial",
      "board": "Pants & Jeans",
      "source": "local",
      "timestamp": "2026-05-12T14:31:30.000000"
    }
  ],
  "steps": [
    {
      "step": 1,
      "title": "Verify Credentials",
      "status": "success",
      "details": "Pinterest: user...@gmail.com\nShopify URL: https://meeeshop.myshopify.com"
    }
    // ... more steps
  ]
}
```

## Troubleshooting

### Step 1: Verify Credentials — FAILED

**Error**: `PINTEREST_EMAIL not set`

**Fix**: Make sure `.env` file exists and contains:
```
PINTEREST_EMAIL=your_email@gmail.com
PINTEREST_PASSWORD=your_password
SHOPIFY_STORE_URL=https://meeeshop.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
STORE_BASE_URL=https://us.meeeshop.com
GEMINI_API_KEY=AIza...
```

### Step 2: Fetch Shopify Product — FAILED

**Error**: `No products found in Shopify`

**Fix**:
1. Check Shopify store has products (go to Products → Products)
2. Verify `SHOPIFY_STORE_URL` is correct
3. Verify `SHOPIFY_ACCESS_TOKEN` is valid (check in Shopify admin)

### Step 3: Generate AI Content — FAILED

**Error**: `Could not generate content`

**Fix**:
1. Check at least one AI key is set: `GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENROUTER_API_KEY`
2. Verify API key is valid (test with `python ai_client.py`)
3. Check API rate limits haven't been exceeded

### Step 4: Optimize Image with Overlays — FAILED

**Error**: `Image optimization failed`

**Fix**:
1. Ensure product image URL is publicly accessible
2. Check internet connection
3. Verify image format is supported (JPG, PNG, WebP)

### Step 5: Select Video for Pin — WARNING

**Status**: `No videos found from any source (will use image only)`

**This is OK** — Video is optional. Product pin will still be created with image.

**To enable video:**
1. Add videos to `meeeshop-youtube/videos/` directory, OR
2. Setup YouTube API credentials in `.env` (optional)

### Step 6: Login to Pinterest — FAILED

**Error**: `Login failed`

**Fix (in order):**
1. **Try saved cookies first** (fastest):
   - Run `python setup_pinterest_login.py` to save fresh cookies
   - Then retry test

2. **Use email/password login**:
   - Ensure credentials are correct
   - If 2FA enabled: Disable temporarily or use app password
   - Try manual login in browser first

3. **Update ChromeDriver**:
   ```powershell
   pip install --upgrade webdriver-manager
   ```

### Step 7: Create Product Pin — FAILED

**Error**: `Pinterest API returned False`

**Fix**:
1. Check Pinterest connection is stable
2. Verify board exists and name is correct
3. Check image is under 5MB and in supported format
4. Try manual pin creation in browser to verify board is accessible

### Step 8: Create Video Pin — FAILED

**Error**: `Could not download YouTube video`

**Fix**:
1. Ensure `yt-dlp` is installed: `pip install yt-dlp`
2. Check internet connection
3. Verify YouTube URL is valid and public
4. Try with local video file instead

## Advanced — Run Individual Tests

### Test Shopify Connection Only
```powershell
python shopify_products.py
```

### Test AI Content Generation
```powershell
python content_generator.py
```

### Test Video Selection
```powershell
python video_picker.py
```

### Test Pinterest Login
```powershell
python pinterest_client.py
```

### Test Image Optimization
```powershell
python image_optimizer.py
```

## Performance Targets

After successful test:
- ✅ Product pin created on relevant board
- ✅ Pin includes optimized image with overlays
- ✅ Rich pin metadata (title, description, URL, alt text)
- ✅ Video pin created (if video available)
- ✅ Test runs in <5 minutes

## Next Steps

1. ✅ Run test: `python test_product_and_video_pins.py`
2. ✅ Check pins on Pinterest (they should appear on your board)
3. ✅ Verify pin quality and content
4. ✅ Once validated, push to GitHub:
   ```bash
   git add test_product_and_video_pins.py
   git commit -m "Add comprehensive product & video pin test"
   git push origin main
   ```
5. ✅ Setup GitHub Actions for daily automated posting
6. ✅ Monitor first week of automated pins

## Log Files

- `test_pins_run.log` — Full test execution log
- `test_results_latest.json` — Structured test results
- `Pinterest_daily.log` — Daily posting logs (if using scheduler)

## Support

If test fails:
1. Check `test_pins_run.log` for detailed error
2. Review credentials in `.env`
3. Try individual component tests (Shopify, AI, Pinterest)
4. Check GitHub issues for similar problems

---

**Created**: 2026-05-12  
**Python**: 3.10+  
**Estimated Time**: 5-10 minutes
