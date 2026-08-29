import os
import sys
import pickle
import json
import base64
import subprocess
from pathlib import Path
from cryptography.fernet import Fernet
from secrets_manager import _get_keys, _load_vault, _double_decrypt

def update_secrets_enc(key: str, value: str):
    primary, fallback = _get_keys()
    
    try:
        vault = _load_vault()
        decrypted_vault = {}
        for k, v in vault.items():
            decrypted_vault[k] = _double_decrypt(v, primary, fallback)
    except Exception as e:
        print(f"Error loading vault: {e}")
        decrypted_vault = {}

    decrypted_vault[key] = value

    new_vault = {}
    for k, v in decrypted_vault.items():
        inner = Fernet(fallback).encrypt(v.encode())
        outer = Fernet(primary).encrypt(inner).decode()
        new_vault[k] = outer
        
    candidate = Path("secrets.enc")
    with open(candidate, "w", encoding="utf-8") as f:
        json.dump(new_vault, f, indent=2)
    print(f"✅ Successfully updated {key} in secrets.enc")

def main():
    print("=" * 70)
    print("🚀 STARTING PINTEREST LOGIN FIX")
    print("=" * 70)
    print("\nA Chrome window will now open.")
    print("Please log into Pinterest in that window.")
    print("Once you log in, this script will automatically capture the session cookies")
    print("and encrypt them into your secrets.enc file.\n")
    
    # Run setup_pinterest_login.py
    result = subprocess.run([sys.executable, "setup_pinterest_login.py"])
    
    if result.returncode != 0:
        print("\n❌ Login failed or was cancelled.")
        sys.exit(1)
        
    # Read the cookies file
    cookies_file = Path(".pinterest_cookies")
    if not cookies_file.exists():
        print("\n❌ Cookies file not found! Login might not have completed.")
        sys.exit(1)
        
    print("\nReading saved cookies...")
    with open(cookies_file, "rb") as f:
        cookies_list = pickle.load(f)
            
    print(f"Extracted {len(cookies_list)} cookies.")
    
    # Base64 encode the full list
    cookies_json = json.dumps(cookies_list)
    cookies_b64 = base64.b64encode(cookies_json.encode('utf-8')).decode('utf-8')
    
    # Update secrets.enc
    update_secrets_enc("PINTEREST_COOKIES_B64", cookies_b64)
    print("\n🎉 ALL DONE! Your Pinterest login is fixed and securely encrypted.")

if __name__ == "__main__":
    main()
