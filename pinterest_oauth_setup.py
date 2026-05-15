"""
pinterest_oauth_setup.py — One-time OAuth 2.0 setup script.

Run this LOCALLY to obtain a Pinterest refresh_token.
Then save the printed refresh_token as the GitHub secret PINTEREST_REFRESH_TOKEN.

Usage:
    python pinterest_oauth_setup.py

Prerequisites:
    - Set PINTEREST_CLIENT_ID and PINTEREST_CLIENT_SECRET in your .env
      or export them in your shell.
    - Add http://localhost:8000/callback as a redirect URI in your
      Pinterest Developer App at https://developers.pinterest.com/apps/
"""

import base64
import http.server
import os
import threading
import urllib.parse
import webbrowser
from dotenv import load_dotenv
import requests

load_dotenv()

CLIENT_ID = os.environ.get("PINTEREST_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("PINTEREST_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8000/callback"
SCOPES = "boards:read,boards:write,pins:read,pins:write,user_accounts:read"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
AUTH_URL = "https://www.pinterest.com/oauth/"

received_code: list = []


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if code:
            received_code.append(code)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorization successful! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code received.</h2>")

    def log_message(self, format, *args):
        pass  # suppress server logs


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set PINTEREST_CLIENT_ID and PINTEREST_CLIENT_SECRET in your .env or shell.")
        return

    # Start local HTTP server in background thread
    server = http.server.HTTPServer(("localhost", 8000), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    # Build authorization URL and open browser
    auth_params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
    })
    auth_url = f"{AUTH_URL}?{auth_params}"
    print(f"\nOpening browser for Pinterest authorization...\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    thread.join(timeout=120)
    if not received_code:
        print("ERROR: No authorization code received within 120 seconds.")
        return

    code = received_code[0]
    print(f"Authorization code received.")

    # Exchange code for tokens
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed: {resp.status_code} {resp.text}")
        return

    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    print("\n" + "=" * 60)
    print("SUCCESS! Save these as GitHub Actions secrets:")
    print("=" * 60)
    print(f"\nPINTEREST_CLIENT_ID     = {CLIENT_ID}")
    print(f"PINTEREST_CLIENT_SECRET = {CLIENT_SECRET}")
    print(f"PINTEREST_REFRESH_TOKEN = {refresh_token}")
    print("\nAccess token (short-lived, for testing only):")
    print(f"  {access_token}")
    print("\nAdd to GitHub Actions secrets at:")
    print("  https://github.com/<your-repo>/settings/secrets/actions")


if __name__ == "__main__":
    main()
