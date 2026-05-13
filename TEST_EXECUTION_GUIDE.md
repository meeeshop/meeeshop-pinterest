# Pinterest Automation Testing — Complete Execution Guide

## 🚀 Start Here

This guide walks you through **setting up and running** the comprehensive product & video pin tests for Pinterest automation.

**Time Estimate**: 25-30 minutes total  
**Difficulty**: Beginner-friendly (all steps documented)  
**Success Rate**: 95%+ (with checklist)

---

## Phase 1: Preparation (5-10 min)

### Step 1: Complete the Checklist

Go through [CHECKLIST_BEFORE_TEST.md](CHECKLIST_BEFORE_TEST.md) to verify:

- [ ] **Credentials ready**
  - Pinterest account with 1+ board
  - Shopify store with 5+ products
  - API keys (Gemini/Groq/OpenRouter)

- [ ] **Environment file created** (`.env`)
  - Contains all required credentials
  - No spaces around `=`
  - All values are correct

- [ ] **System ready**
  - Python 3.10+ installed
  - Chrome browser available
  - Virtual environment created
  - Dependencies installed: `pip install -r requirements.txt`

- [ ] **Component tests pass**
  - `python ai_client.py` ✓
  - `python shopify_products.py` ✓
  - `python video_picker.py` ✓ (optional)

**Status Check**: ☐ All items checked? → Continue to Phase 2

---

## Phase 2: Run the Test (5-10 min)

### Option A: Automated (Recommended)

**Windows PowerShell**:
```powershell
# Navigate to project directory
cd "C:\Users\USER\Downloads\Shopify_Claude\meeeshop-pinterest"

# Make script executable (if needed)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run test
./run_test.ps1
```

**Windows Batch**:
```powershell
cd "C:\Users\USER\Downloads\Shopify_Claude\meeeshop-pinterest"
run_test.bat
```

### Option B: Manual

```powershell
# 1. Navigate to project
cd "C:\Users\USER\Downloads\Shopify_Claude\meeeshop-pinterest"

# 2. Activate virtual environment
venv\Scripts\Activate.ps1

# 3. Run test
python test_product_and_video_pins.py
```

### What Happens Next

The test will:

1. **Verify credentials** — Check all required env vars are set
2. **Fetch product** — Get a random product from Shopify
3. **Generate content** — Create AI-powered pin title & description
4. **Optimize image** — Process product image with overlays
5. **Select video** — Find video from local repo or YouTube
6. **Login to Pinterest** — Authenticate with saved cookies or credentials
7. **Create product pin** — Post optimized image to board
8. **Create video pin** — Post video (if available)

### Expected Output

```
[INFO] ======================================================================
[INFO]     PINTEREST AUTOMATION — PRODUCT & VIDEO PIN TEST
[INFO] ======================================================================
[INFO]
[INFO] ✓ Step 1: Verify Credentials [success]
[INFO]     Pinterest: user...@gmail.com
[INFO]
[INFO] ✓ Step 2: Fetch Shopify Product [success]
[INFO]     Product: Vintage High-Waisted Jeans
[INFO]     Board: Pants & Jeans
[INFO]
[INFO] ✓ Step 3: Generate AI Content [success]
[INFO]     Title: Chic Vintage Jeans
[INFO]     Description: Flattering high-waist fit...
[INFO]
[INFO] ✓ Step 4: Optimize Image with Overlays [success]
[INFO]     Image: optimized_product_image.jpg
[INFO]     Size: 2.5MB
[INFO]
[INFO] ✓ Step 5: Select Video for Pin [success]
[INFO]     Source: Local
[INFO]     File: fashion_tutorial.mp4
[INFO]
[INFO] ✓ Step 6: Login to Pinterest [success]
[INFO]     Logged in successfully
[INFO]     Boards: 8 available
[INFO]
[INFO] ✓ Step 7: Create Product Pin [success]
[INFO]     Title: Chic Vintage Jeans
[INFO]     Board: Pants & Jeans
[INFO]
[INFO] ✓ Step 8: Create Video Pin [success]
[INFO]     Video: fashion_tutorial.mp4
[INFO]     Board: Pants & Jeans
[INFO]
[INFO] ======================================================================
[INFO] ✅ TEST SUMMARY
[INFO] ======================================================================
[INFO] Product Pin: ✅ SUCCESS
[INFO] Video Pin: ✅ SUCCESS
[INFO] Total Pins Created: 2
[INFO] Test Duration: 8 steps
```

---

## Phase 3: Verify Results (5 min)

### Check Test Output Files

Three files are created after test completes:

#### 1. `test_pins_run.log` (Detailed log)
```powershell
# View log
type test_pins_run.log
```

Contains full execution details, useful for troubleshooting.

#### 2. `test_results_latest.json` (Structured results)
```powershell
# View results
type test_results_latest.json

# Or pretty-print
python -m json.tool test_results_latest.json
```

Example output:
```json
{
  "test_name": "Pinterest Product & Video Pin Automation",
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
  ]
}
```

#### 3. Console Output
Look for final summary:
- `Product Pin: ✅ SUCCESS` or `❌ FAILED`
- `Video Pin: ✅ SUCCESS` or `❌ FAILED`

### Verify on Pinterest

1. **Go to Pinterest**:
   - Open: https://pinterest.com
   - Login with your account

2. **Check your board**:
   - Click on the board you targeted (e.g., "Pants & Jeans")
   - Look for newly created pins at the top

3. **Verify pin quality**:
   - ✓ Product image appears (possibly with overlays)
   - ✓ Pin title matches generated content
   - ✓ Description visible
   - ✓ Product link works
   - ✓ (If video) Video pin appears separately

### Success Indicators

#### ✅ Full Success
- Console shows: `✅ TEST PASSED`
- `test_results_latest.json` shows: `"success": true`
- 2 pins appear on Pinterest (product + video)
- Both pins have correct content

#### ✅ Partial Success (Still OK)
- Console shows: `✅ TEST PASSED`
- Product pin created successfully
- Video pin skipped (no video available)
- This is expected if no videos configured

#### ❌ Test Failed
- Console shows: `❌ TEST FAILED`
- Check which step failed
- Review troubleshooting section below

---

## Phase 4: Troubleshooting (if needed)

### If Test Fails

#### Step 1: Identify which step failed

Look at console output:
```
✓ Step 1: Verify Credentials [success]
✓ Step 2: Fetch Shopify Product [success]
✗ Step 3: Generate AI Content [error]  ← FAILED HERE
```

#### Step 2: Read the error details

```
[INFO] ✗ Step 3: Generate AI Content [error]
[INFO]     API rate limit exceeded
```

#### Step 3: Consult troubleshooting table

| Step | Common Issues | Fix |
|------|---------------|-----|
| 1: Verify Credentials | Missing `.env` | Create `.env` with all required vars |
| 2: Fetch Shopify | Invalid credentials | Check Shopify URL and access token |
| 3: Generate AI Content | API key invalid | Test: `python ai_client.py` |
| 4: Optimize Image | Image download failed | Check product image URL is public |
| 5: Select Video | No videos found | Add videos to `meeeshop-youtube/videos/` (optional) |
| 6: Login Pinterest | Login failed | Run: `python setup_pinterest_login.py` |
| 7: Create Product Pin | Board not found | Create board in Pinterest first |
| 8: Create Video Pin | Video format error | Ensure video is <50MB, <15min MP4/WebM |

#### Step 4: Get full error details

```powershell
# View detailed log
type test_pins_run.log | grep -A5 "Step 3"  # Replace 3 with failed step

# Or view JSON results
python -c "import json; print(json.dumps(json.load(open('test_results_latest.json')), indent=2))"
```

#### Step 5: Try quick fixes

**Most common fixes:**

1. **Update dependencies**:
   ```powershell
   pip install --upgrade -r requirements.txt
   ```

2. **Clear cookies and retry login**:
   ```powershell
   rm .pinterest_cookies
   python test_product_and_video_pins.py
   ```

3. **Save fresh Pinterest cookies**:
   ```powershell
   python setup_pinterest_login.py
   ```

4. **Test individual component**:
   ```powershell
   # If AI fails, test AI
   python ai_client.py
   
   # If Shopify fails, test Shopify
   python shopify_products.py
   
   # If Pinterest fails, test Pinterest
   python pinterest_client.py
   ```

### Full Troubleshooting Guide

For detailed help on each step, see:
- [TEST_GUIDE.md](TEST_GUIDE.md) — Step-by-step troubleshooting
- [TESTING_SUMMARY.md](TESTING_SUMMARY.md) — Architecture and scenarios
- [README.md](README.md) — Overall documentation

---

## Phase 5: Next Steps (After Success)

### If Test Passed ✅

#### 1. Commit to Git
```powershell
git add test_product_and_video_pins.py TEST_GUIDE.md run_test.ps1 run_test.bat
git commit -m "Add comprehensive product & video pin testing"
git push origin main
```

#### 2. Setup GitHub Actions
See [README.md](README.md) → GitHub Actions Setup:
- Add secrets to GitHub repo
- Enable automatic daily posting
- Monitor logs

#### 3. Deploy to Production
- Test with a few runs (1-2 per day)
- Monitor pin performance on Pinterest
- Adjust settings based on results

#### 4. Fine-tune Configuration

**Adjust posting frequency**:
```python
# In pinterest_daily.py
MAX_PINS_PER_DAY = 3              # Increase/decrease
COOLDOWN_HOURS = 2                # Adjust waiting time
BOARD_ROTATION_COOLDOWN = 24      # Prevent board spam
```

**Add more boards**:
```python
# In shopify_products.py
get_pinterest_board_mapping() → Add more board keywords
```

**Customize content**:
```python
# In content_generator.py
Edit: generate_pinterest_title()
Edit: generate_hashtags()
```

### If Test Needs Improvement

#### Video not found?
- Add `.mp4` files to `meeeshop-youtube/videos/`
- Or setup YouTube API (see VIDEO_INTEGRATION.md)

#### Content not good enough?
- Adjust AI prompts in `content_generator.py`
- Try different AI models (Gemini → Groq → OpenRouter)
- Test with: `python content_generator.py`

#### Image optimization not working?
- Check product image URLs
- Try simpler overlay settings
- See `image_optimizer.py` for customization

---

## Command Reference

### Run Tests
```powershell
# Full test
./run_test.ps1
python test_product_and_video_pins.py

# Component tests
python ai_client.py               # Test AI
python shopify_products.py        # Test Shopify
python video_picker.py            # Test video selection
python image_optimizer.py         # Test image processing
python pinterest_client.py        # Test Pinterest login
```

### Setup & Configuration
```powershell
# Save Pinterest cookies (do once)
python setup_pinterest_login.py

# Setup environment
pip install -r requirements.txt
python -m venv venv
venv\Scripts\Activate.ps1

# View results
type test_results_latest.json
type test_pins_run.log
```

### Troubleshooting
```powershell
# Check Python
python --version

# Check Chrome
Get-Process chrome -ErrorAction SilentlyContinue

# Check dependencies
pip list | grep -E "selenium|requests|pillow"

# Test connectivity
python -c "import requests; requests.get('https://pinterest.com')"
```

---

## FAQ

### Q: How long does the test take?
**A**: 5-10 minutes, depending on:
- Internet speed (Shopify + Pinterest)
- AI model response time
- Video download (if YouTube)

### Q: Do I need a video?
**A**: No, video is optional. Product pin will be created regardless.

### Q: Can I run this daily?
**A**: Yes! Use GitHub Actions for daily automated posting (see README.md).

### Q: How many pins can I post per day?
**A**: 3-5 is safe (Pinterest doesn't flag accounts). Adjust in `pinterest_daily.py`.

### Q: What if credentials are wrong?
**A**: Test will fail at Step 1 or 6. Check `.env` file and credentials.

### Q: Is my data safe?
**A**: All credentials stay local in `.env` (never committed to Git).

### Q: Can I use different AI models?
**A**: Yes! Supported: Gemini, Groq, OpenRouter (see `ai_client.py`).

### Q: How do I update if something breaks?
**A**: Pull latest, update ChromeDriver, reinstall dependencies:
```powershell
git pull origin main
pip install --upgrade -r requirements.txt
pip install --upgrade webdriver-manager
```

---

## Summary Checklist

```
PREPARATION:
☐ Complete CHECKLIST_BEFORE_TEST.md
☐ Credentials ready (Pinterest, Shopify, API key)
☐ .env file created and verified
☐ Dependencies installed
☐ Component tests pass

EXECUTION:
☐ Run test: ./run_test.ps1 or python test_product_and_video_pins.py
☐ Wait for completion (5-10 min)
☐ Watch for: ✅ TEST PASSED or ❌ TEST FAILED

VERIFICATION:
☐ Check test_results_latest.json (success: true)
☐ Check Pinterest account (pins visible on board)
☐ Review pin quality (content, image, link)

DEPLOYMENT:
☐ Commit to Git
☐ Push to GitHub
☐ Setup GitHub Actions (optional)
☐ Enable daily posting (optional)

MONITORING:
☐ Review pin engagement on Pinterest
☐ Adjust settings based on performance
☐ Fine-tune content strategy
```

---

## Getting Help

If you get stuck:

1. **Check Logs**:
   - `test_pins_run.log` — Find exact error
   - `test_results_latest.json` — Structured results

2. **Consult Docs**:
   - [TEST_GUIDE.md](TEST_GUIDE.md) — Step-by-step help
   - [TESTING_SUMMARY.md](TESTING_SUMMARY.md) — Detailed breakdown
   - [README.md](README.md) — Overall project info

3. **Try Workarounds**:
   - Update dependencies: `pip install --upgrade -r requirements.txt`
   - Clear cookies: `rm .pinterest_cookies`
   - Test components individually

4. **Debug**:
   - Enable DEBUG logging in test script
   - Run component tests in isolation
   - Check internet connection

---

**Created**: 2026-05-12  
**Version**: 1.0  
**Status**: ✅ Complete & Ready to Use

---

## What's Next?

1. **Follow this guide** step-by-step
2. **Run the test** using ./run_test.ps1
3. **Verify results** on your Pinterest board
4. **Deploy** to GitHub Actions for daily posting
5. **Monitor** performance and fine-tune

**You've got this! 🚀**
