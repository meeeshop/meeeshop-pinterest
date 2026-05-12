# Quick Start — 10 Minutes to Automated Pinterest Posting

## 1. Get API Keys (3 min)

Pick **one** (easiest to hardest):

### 🟢 Google Gemini (Easiest)
- Go: https://aistudio.google.com
- Click "Get API Key" → Create API key
- Copy to `.env`

### 🟡 Groq (Fast)
- Go: https://console.groq.com
- Sign up → API Keys → Create
- Copy to `.env`

### 🔵 OpenRouter (Most models)
- Go: https://openrouter.ai
- Sign up → Keys → Create
- Copy to `.env`

## 2. Fill .env (2 min)

```powershell
notepad .env
```

```
PINTEREST_EMAIL=your_email@gmail.com
PINTEREST_PASSWORD=your_password
SHOPIFY_STORE_URL=https://meeeshop.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
STORE_BASE_URL=https://us.meeeshop.com
GEMINI_API_KEY=AIza...
```

## 3. Install & Test (3 min)

```powershell
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Test
python ai_client.py              # Should show "OK"
python shopify_products.py       # Should show products
python content_generator.py      # Should show AI content
```

## 4. Run (2 min)

```powershell
python pinterest_daily.py
```

Watch Chrome open → Login → Post to Pinterest ✅

## 5. GitHub Actions (Optional)

```powershell
git remote add origin https://github.com/YOUR_USERNAME/meeeshop-pinterest
git push -u origin main
```

Then add secrets in GitHub repo settings:
- PINTEREST_EMAIL
- PINTEREST_PASSWORD
- SHOPIFY_STORE_URL
- SHOPIFY_ACCESS_TOKEN
- GEMINI_API_KEY

Runs automatically daily at 2 PM UTC ✅

---

## Troubleshooting (30 sec)

| Issue | Fix |
|-------|-----|
| Python not found | Download from python.org, reinstall |
| API key invalid | Test with `python ai_client.py` |
| Pinterest login fails | Try manual login in browser, check 2FA |
| No products shown | Check SHOPIFY_STORE_URL and token |
| ChromeDriver fails | `pip install --upgrade webdriver-manager` |

---

**Full Guide**: See [SETUP_GUIDE.md](SETUP_GUIDE.md)
**Details**: See [README.md](README.md)
