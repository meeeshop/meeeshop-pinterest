#!/usr/bin/env python3
import pickle
from pathlib import Path

pkl_file = Path(__file__).parent / ".pinterest_cookies.pkl"
with open(pkl_file, "rb") as f:
    cookies = pickle.load(f)
    print(f"Total cookies: {len(cookies)}")
    for c in cookies:
        print(f"  - {c['name']}: {c['value'][:50]}...")
