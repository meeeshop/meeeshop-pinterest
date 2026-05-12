# Pinterest Credentials Guide — 4 Ways to Login

Your concern is valid! Here are **4 secure methods** to handle Pinterest credentials:

## Option 1: .env File (Simple, Recommended for First Run)

**How it works:**
- Store email/password in `.env` file
- Script reads from file at startup
- File is in `.gitignore` (never committed)

**Setup:**
```powershell
cp .env.example .env
notepad .env
```

```env
PINTEREST_EMAIL=your_email@gmail.com
PINTEREST_PASSWORD=your_password
```

**Pros:**
- ✅ Simple & straightforward
- ✅ Works immediately
- ✅ Credentials never exposed online

**Cons:**
- ❌ Password stored in plaintext on disk
- ⚠️ Use a temporary password, not your main one

---

## Option 2: Saved Cookies (Best - No Password Needed!)

**How it works:**
1. First run: Browser opens, **you log in manually** (no password entry in script)
2. Script saves Pinterest cookies to file
3. Future runs: Use saved cookies (auto-login, **no password needed**)

**Setup:**

### First Time Only:
```powershell
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
```

This will:
- ✅ Open Chrome browser
- ✅ Show Pinterest login page
- ✅ **YOU type password** (script never sees it)
- ✅ After login, cookies auto-saved
- ✅ Browser closes

### Every Run After That:
```powershell
python pinterest_daily.py
```

It automatically uses saved cookies — **no password needed!**

**Pros:**
- ✅✅ **Most secure** — password never stored
- ✅ No password entry in automation
- ✅ Google Authenticator/2FA still works
- ✅ Session valid for weeks
- ✅ **Recommended method**

**Cons:**
- ⚠️ Cookies expire after ~30 days (need to re-login occasionally)
- ⚠️ If you change password, need fresh login

**Files Created:**
- `.pinterest_cookies` — Binary pickle file (not readable)
- `.pinterest_session` — Session token

---

## Option 3: Chrome Profile (Browser Already Logged In)

**How it works:**
- Script uses your Chrome profile that's already logged into Pinterest
- No password needed anywhere

**Setup:**

### Step 1: Logout of Chrome
Close all Chrome windows.

### Step 2: Check Profile:
```powershell
# Find your Chrome profile location:
$profile = "$env:APPDATA\..\Local\Google\Chrome\User Data\Default"
echo $profile
```

### Step 3: Update pinterest_client.py
```python
from credentials_manager import ChromeProfileManager

profile_path = ChromeProfileManager.get_user_profile_path()
options = ChromeProfileManager.create_options_with_profile(profile_path)

client = PinterestClient(headless=False)
# ... rest of code
```

**Pros:**
- ✅ **Ultra secure** — no password anywhere
- ✅ Browser settings/history included
- ✅ 2FA already setup

**Cons:**
- ❌ Complex to setup
- ❌ Chrome must be fully closed before run
- ❌ Profile tied to one computer

---

## Option 4: Environment Variables (CI/CD)

**How it works:**
- Set credentials as system environment variables
- Script reads from `$env:PINTEREST_EMAIL` / `$env:PINTEREST_PASSWORD`

**Setup (Windows):**
```powershell
# Set for current session only:
$env:PINTEREST_EMAIL = "your_email@gmail.com"
$env:PINTEREST_PASSWORD = "your_password"

# Set permanently (in System environment variables):
# Settings → System → Environment variables → Edit PINTEREST_EMAIL
```

**Setup (GitHub Actions):**
```yaml
# In workflow file:
env:
  PINTEREST_EMAIL: ${{ secrets.PINTEREST_EMAIL }}
  PINTEREST_PASSWORD: ${{ secrets.PINTEREST_PASSWORD }}
```

**Pros:**
- ✅ Good for CI/CD pipelines
- ✅ GitHub stores as encrypted secrets
- ✅ Secrets not in code

**Cons:**
- ⚠️ Credentials in memory
- ⚠️ Visible in environment if inspected

---

## Security Comparison

| Method | Security | Setup | Convenience | Recommended |
|--------|----------|-------|-------------|------------|
| .env File | ⚠️ Medium | ⭐⭐ Easy | ⭐⭐ | ✓ For testing |
| Saved Cookies | ✅✅ High | ⭐⭐ Easy | ⭐⭐⭐ | ✓✓ **Best** |
| Chrome Profile | ✅✅ High | ⭐ Hard | ⭐⭐ | For advanced |
| Environment Vars | ✅ High | ⭐⭐ Easy | ⭐⭐⭐ | ✓ For GitHub Actions |

---

## How to Choose

### For Local Testing/Development:
```
1. First run: python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
2. Every run after: python pinterest_daily.py
✅ Most secure, no password stored
```

### For GitHub Actions (CI/CD):
```
1. Add PINTEREST_EMAIL & PINTEREST_PASSWORD to GitHub Secrets
2. Workflow uses: ${{ secrets.PINTEREST_EMAIL }}
3. Script reads from environment variables
✅ Encrypted at rest, in GitHub vault
```

### For Production Server:
```
1. Save cookies once (interactive login)
2. Copy .pinterest_cookies to server
3. Every run uses saved cookies (no password needed)
✅ Password never touches server
```

---

## How Saved Cookies Work

When you login to Pinterest:
```
Browser (You type password) 
    ↓
Pinterest servers (verify password)
    ↓
Return cookies to browser
    ↓
Script saves cookies to file (.pinterest_cookies)
    ↓
Every future run: Use cookies directly
```

**What's in the cookies:**
- Session ID (proves you're logged in)
- User preferences
- CSRF token (prevents forgery)

**What's NOT in cookies:**
- ❌ Your password
- ❌ Credit card info
- ❌ Personal messages
- ❌ Account recovery codes

**Cookie expiration:**
- Typical: 30-60 days
- If used regularly: Stays valid
- If unused: Expires after ~30 days
- Just re-run interactive login when needed

---

## Best Practice: Hybrid Approach

1. **First Setup** (one-time):
   ```powershell
   python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
   ```
   Creates `.pinterest_cookies` file

2. **Daily Runs** (automated):
   ```powershell
   python pinterest_daily.py
   ```
   Uses saved cookies, no password needed

3. **Monthly Maintenance** (when cookies expire):
   ```powershell
   python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
   ```
   Re-login to refresh cookies

---

## Troubleshooting

### "Login failed" with saved cookies
**Solution**: Cookies expired, re-run interactive login:
```powershell
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
```

### "Chrome browser didn't open"
**Solution**: Check ChromeDriver:
```powershell
pip install --upgrade webdriver-manager
python -c "from webdriver_manager.chrome import ChromeDriverManager; ChromeDriverManager().install()"
```

### "Manual login timed out"
**Solution**: You took >5 minutes to login. Re-run and login faster:
```powershell
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"
```

### ".pinterest_cookies file is empty"
**Solution**: Login wasn't detected. Make sure:
- You actually clicked login
- Wait for home feed to appear
- Then script auto-saves

---

## File Permissions & Security

### .env File (.gitignore)
```
.env                    # Never committed to git
.env.local              # For local overrides
.env.*.local            # For environment-specific
```

### .pinterest_cookies (Binary)
```
.pinterest_cookies      # Binary pickle file
                        # Not readable as text
                        # Contains only session data
                        # NOT your password
```

### .pinterest_session (Token)
```
.pinterest_session      # Session token string
                        # Used for validation
                        # Expires with cookies
```

---

## For GitHub/Sharing

✅ **Safe to commit:**
- ✓ Code files (.py)
- ✓ Docs (.md)
- ✓ Configuration templates (.env.example)
- ✓ .gitignore (lists what to exclude)

❌ **Never commit:**
- ✗ .env (real credentials)
- ✗ .pinterest_cookies (session data)
- ✗ .pinterest_session (token)
- ✗ Any file with actual passwords

**Check before pushing:**
```powershell
git status
# Should NOT show .env, .pinterest_*, posting_history.json
```

---

## Advanced: Store in System Keyring

(Optional, most secure for Windows/Mac/Linux)

```python
import keyring

# Save password:
keyring.set_password("pinterest-automation", "email@gmail.com", "your_password")

# Load password:
password = keyring.get_password("pinterest-automation", "email@gmail.com")
```

Install: `pip install keyring`

---

## Summary

| Scenario | Method |
|----------|--------|
| Local testing | **Saved Cookies** (interactive login once) |
| GitHub Actions | **GitHub Secrets** (encrypted) |
| Production Server | **Saved Cookies** (from local setup) |
| Maximum Security | **Chrome Profile** (advanced) |
| Quick Testing | **.env file** (temporary only) |

**Recommended Starting Point:**
```powershell
# One-time setup:
python -c "from credentials_manager import interactive_login_and_save; interactive_login_and_save()"

# Then daily:
python pinterest_daily.py
```

---

**Questions?** Check `pinterest_client.py` → `login()` method to see how it tries each method in order.
