# 🚀 MeeeShop Pinterest Automation — START HERE

Welcome! This guide will get you posting to Pinterest daily in **less than 1 hour**.

---

## What This Does

✅ Posts Shopify products to Pinterest daily  
✅ AI-generates catchy titles & descriptions  
✅ Routes to relevant boards automatically  
✅ Uses safe, tested anti-block safeguards  
✅ Runs fully automated via GitHub Actions  
✅ $0/month (all free services)  

**Result:** Organic traffic from 100M+ Pinterest women shoppers → Your store

---

## 5-Minute Decision Tree

```
I want to...                          → Go to...
├─ Get running in 10 minutes         → QUICK_START.md
├─ Understand how it works           → HOW_CREDENTIALS_WORK.md
├─ Step-by-step 1-hour setup         → SETUP_GUIDE.md
├─ Know what was built               → README.md
├─ See technical details             → ARCHITECTURE.md
├─ Handle credentials securely       → CREDENTIALS_GUIDE.md
└─ Understand 4 login methods        → HOW_CREDENTIALS_WORK.md
```

---

## Your Question Answered

> "How does it get my email and password... can it use from cookie or refresh token from chrome"

**YES! Here's the secure way:**

### Option A: Saved Cookies (Recommended ⭐⭐⭐)
```powershell
# First time only (5 minutes):
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
# → Browser opens, YOU log in manually, cookies saved

# Every time after (fully automated):
python pinterest_daily.py
# → Uses saved cookies, no password needed!
```

**Advantages:**
- ✅ Password never stored
- ✅ Password never in script
- ✅ Works with 2FA
- ✅ Most secure & convenient

### Option B: .env File (Simple)
```powershell
cp .env.example .env
notepad .env
# Fill in: PINTEREST_EMAIL=... PINTEREST_PASSWORD=...

python pinterest_daily.py
```

⚠️ Uses plaintext password (okay for testing, use temp password)

### Option C: GitHub Actions (Automated)
```powershell
# Add secrets in GitHub repo settings
git push origin main
# Runs daily at 2 PM UTC automatically
```

✅ GitHub encrypts secrets, cookies saved for future runs

**👉 Recommended:** Use Option A (saved cookies) + Option C (GitHub Actions)

---

## Quick Start (Choose Your Path)

### 🟢 Path 1: Just Run It Locally (10 min)

```powershell
# 1. Navigate to repo
cd C:\Users\USER\Downloads\Shopify_Claude\meeeshop-pinterest

# 2. Setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 3. Login once (saves cookies)
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"

# 4. Test
python pinterest_daily.py
# → Watch Chrome open, post to Pinterest ✅

# 5. Schedule (Windows Task Scheduler)
# Create task to run: python C:\...\pinterest_daily.py
# Daily at 2 PM
```

### 🟡 Path 2: GitHub Actions (Fully Automated, 15 min)

```powershell
# 1. Same setup as above (steps 1-2)

# 2. Login once
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"

# 3. Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/meeeshop-pinterest
git push -u origin main

# 4. Add secrets in GitHub
# Repo settings → Secrets → Add: PINTEREST_EMAIL, PINTEREST_PASSWORD, etc.

# 5. Done!
# Posts automatically every day at 2 PM UTC ✅
```

### 🔵 Path 3: Both Local + GitHub (Recommended, 20 min)

1. Run locally first (test & verify it works)
2. Push to GitHub (backup + automated)
3. GitHub Actions posts daily automatically
4. Monitor via GitHub Actions logs

---

## Files Overview

| File | Read When |
|------|-----------|
| **00_START_HERE.md** | You are here! 👈 |
| **QUICK_START.md** | Want 10-min summary |
| **HOW_CREDENTIALS_WORK.md** | Want to understand cookies/tokens |
| **SETUP_GUIDE.md** | Want step-by-step 1-hour walkthrough |
| **CREDENTIALS_GUIDE.md** | Want all 4 login methods explained |
| **README.md** | Want complete feature documentation |
| **ARCHITECTURE.md** | Want technical details |
| **pinterest_daily.py** | Want to read the main code |

---

## What You Need (Right Now)

### ✅ Pinterest Account
- Email & password (or use manual login + cookies)
- 3-4 boards already created (or script discovers them)

### ✅ Shopify Store  
- Store URL: `https://meeeshop.myshopify.com`
- API token: From Shopify admin (takes 1 min to create)

### ✅ One Free AI API Key (Pick One)
- **Google Gemini** (easiest): https://aistudio.google.com
- **Groq** (fast): https://console.groq.com  
- **OpenRouter** (most models): https://openrouter.ai

### ✅ Chrome Browser
- Installed on your computer
- Will be auto-managed by script

---

## Credentials Setup (3 Ways)

### Way 1: Saved Cookies (Recommended) ⭐
```powershell
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
```
- Browser opens, you log in manually
- Cookies saved to `.pinterest_cookies`
- Future runs use cookies (no password needed)

### Way 2: .env File (Simple)
```powershell
notepad .env
# Add: PINTEREST_EMAIL=... PINTEREST_PASSWORD=...
```
- Script reads from `.env`
- Use temp password (not main account)

### Way 3: GitHub Secrets (CI/CD)
```
GitHub Settings → Secrets → Add PINTEREST_EMAIL, PINTEREST_PASSWORD
```
- Encrypted at rest in GitHub
- Runs in secure container

**Choose One → Move Forward**

---

## Timeline to Success

```
Minute 0-5:       Read this file ✅
Minute 5-10:      Get API keys (Gemini/Groq)
Minute 10-15:     Install dependencies
Minute 15-20:     Configure credentials
Minute 20-30:     Test components
Minute 30-40:     Run first post (verify it works)
Minute 40-50:     (Optional) Push to GitHub
Minute 50-60:     (Optional) Add GitHub secrets

✅ Total: ~1 hour to full automation
```

---

## Next Steps (In Order)

### Step 1: Get API Key (3 min)
Pick ONE from:
- Google Gemini: https://aistudio.google.com → "Get API Key"
- Groq: https://console.groq.com → API Keys → Create
- OpenRouter: https://openrouter.ai → Sign up → Keys

### Step 2: Setup Repository (5 min)
```powershell
cd C:\Users\USER\Downloads\Shopify_Claude\meeeshop-pinterest
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Configure Credentials (5 min)
Choose ONE method:
```powershell
# Method A: Saved cookies (recommended)
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"

# OR Method B: .env file
cp .env.example .env
notepad .env  # Fill in PINTEREST_EMAIL, PINTEREST_PASSWORD, etc.
```

### Step 4: Test Components (10 min)
```powershell
python ai_client.py              # Should show "OK"
python shopify_products.py       # Should show 5 products
python content_generator.py      # Should show AI content
```

### Step 5: Run Full Test (10 min)
```powershell
python pinterest_daily.py
# Watch: Chrome opens → Login (or uses cookies) → Post to Pinterest
```

### Step 6: (Optional) GitHub Actions (10 min)
```powershell
git remote add origin https://github.com/YOUR_USERNAME/meeeshop-pinterest
git push -u origin main
# Add PINTEREST_EMAIL, PINTEREST_PASSWORD, SHOPIFY_* to GitHub Secrets
# Daily posts now automated! ✅
```

---

## How It Works (30-Second Overview)

```
Daily Flow:
1. Load credentials (from cookies, .env, or env vars)
2. Login to Pinterest (uses saved cookies if available)
3. Fetch your Pinterest boards (discovers board names)
4. Fetch products from Shopify (gets product data)
5. Select random product (that hasn't been posted yet)
6. Generate AI content (title, description, hashtags)
7. Match to correct board (by product type/tags)
8. Create pin (Selenium posts to Pinterest)
9. Save to history (avoid duplicate posts)

Safety:
- Max 3 pins/day (very safe from blocks)
- 2-hour cooldown between posts (mimics human)
- Board rotation (don't post same board twice in 24h)
- Anti-bot features (bypass detection, normal user-agent)

Result: Organic reach to 100M+ women shoppers on Pinterest
```

---

## Success Checklist

After setup, verify:
- [ ] API key works (`python ai_client.py` shows OK)
- [ ] Shopify connection works (`python shopify_products.py` shows products)
- [ ] Content generation works (`python content_generator.py` shows titles/descriptions)
- [ ] First pin posted successfully (`python pinterest_daily.py`)
- [ ] `posting_history.json` created (tracks posts)
- [ ] `.pinterest_cookies` created (if using cookie method)
- [ ] GitHub Actions enabled (if using GitHub)

---

## Costs

| Component | Cost |
|-----------|------|
| Pinterest | Free (your account) |
| Shopify API | Free (included with store) |
| AI (Gemini) | Free (1M tokens/day) |
| GitHub Actions | Free (2,000 min/month) |
| Python | Free (open-source) |
| Chrome | Free (installed) |
| **TOTAL** | **$0/month** ✅ |

---

## Recommended Reading Order

1. **This file** (START_HERE.md) — Overview
2. **HOW_CREDENTIALS_WORK.md** — Understand cookies
3. **QUICK_START.md** — 10-min summary
4. **SETUP_GUIDE.md** — Detailed step-by-step
5. **README.md** — Full documentation
6. **ARCHITECTURE.md** — If curious about internals

---

## Common Questions

**Q: Do I need to store my password?**  
A: No! Use saved cookies instead. See HOW_CREDENTIALS_WORK.md

**Q: Will Pinterest block me?**  
A: Very unlikely. We use safe limits (3/day) and anti-detection. See README.md

**Q: How long does it take?**  
A: Setup: 1 hour. Daily: 30-50 seconds. Maintenance: 5 min/week.

**Q: Can I use videos?**  
A: Yes! Script can use videos from meeeshop-youtube. See README.md

**Q: Does it work with 2FA?**  
A: Yes! Use saved cookies method. See CREDENTIALS_GUIDE.md

**Q: How much does it cost?**  
A: $0/month (all free services). See above.

---

## Troubleshooting

### Issue: "API key not working"
**Fix:** `python ai_client.py` to test providers

### Issue: "Pinterest login fails"
**Fix:** See CREDENTIALS_GUIDE.md → "Troubleshooting" section

### Issue: "No products found"
**Fix:** Check `SHOPIFY_STORE_URL` and `SHOPIFY_ACCESS_TOKEN` in .env

### Issue: "Chrome not found"
**Fix:** `pip install --upgrade webdriver-manager`

More help: See **SETUP_GUIDE.md** → Troubleshooting section

---

## You're Ready! 🎉

Pick your path above and follow the steps. Most people finish in 1 hour.

**Questions?** Read the relevant `.md` file first (there's a guide for everything).

**Ready?** → Go to **QUICK_START.md** for the fastest path, or **SETUP_GUIDE.md** for detailed walkthrough.

---

## Repository Structure

```
meeeshop-pinterest/
├── 📖 00_START_HERE.md              ← You are here
├── 📖 QUICK_START.md                ← 10-min version
├── 📖 HOW_CREDENTIALS_WORK.md       ← Cookies & tokens
├── 📖 SETUP_GUIDE.md                ← Full 1-hour guide
├── 📖 CREDENTIALS_GUIDE.md          ← All 4 login methods
├── 📖 README.md                     ← Complete docs
├── 📖 ARCHITECTURE.md               ← Technical design
├── 🐍 pinterest_daily.py            ← Main script
├── 🐍 pinterest_client.py           ← Selenium automation
├── 🐍 shopify_products.py           ← Product fetcher
├── 🐍 content_generator.py          ← AI content
├── 🐍 ai_client.py                  ← Free AI provider
├── 🐍 credentials_manager.py        ← Secure credentials
├── 📋 requirements.txt               ← Dependencies
├── 📋 .env.example                  ← Template
├── 📋 .gitignore                    ← What not to commit
└── 📁 .github/workflows/            ← GitHub Actions
```

---

**Status**: ✅ Complete & Ready  
**Created**: 2026-05-12  
**Maintained By**: MeeeShop Automation Team

**Let's get your Pinterest automation running!** 🚀
