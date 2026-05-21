#!/usr/bin/env python3
"""
secrets_manager.py — Double-Fernet runtime decryption with SecretSanitizer and audit trail.

Double encryption: Fernet(PRIMARY).encrypt(Fernet(FALLBACK).encrypt(plaintext))
Both ENCRYPTION_KEY_PRIMARY and ENCRYPTION_KEY_FALLBACK must be set.

Usage:
    from secrets_manager import get_secret, get_all_secrets, inject_to_env
    token = get_secret("SHOPIFY_ACCESS_TOKEN")
"""

import logging
import os
import json
import sys
import datetime
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    print("ERROR: cryptography package missing. Run: pip install cryptography")
    sys.exit(1)


# ── SecretSanitizer ────────────────────────────────────────────────────────────

class SecretSanitizer(logging.Filter):
    """Scrubs decrypted secret values from all log records."""

    _values: set[str] = set()

    @classmethod
    def register(cls, value: str) -> None:
        if value:
            cls._values.add(value)

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for secret in self.__class__._values:
            if secret in msg:
                record.msg = record.msg.replace(secret, "***")
                record.args = ()
        return True


def _install_sanitizer() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(SecretSanitizer())
    # Also attach to root so future handlers inherit it
    root.addFilter(SecretSanitizer())


_sanitizer_installed = False


# ── Key loading ───────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load PRIMARY and FALLBACK keys from .env if not already in environment."""
    for candidate in [Path(__file__).with_name(".env"), Path(".env")]:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"')
            if key in ("ENCRYPTION_KEY_PRIMARY", "ENCRYPTION_KEY_FALLBACK"):
                os.environ.setdefault(key, val)


def _get_keys() -> tuple[bytes, bytes]:
    _load_dotenv()
    primary = os.environ.get("ENCRYPTION_KEY_PRIMARY", "").strip()
    fallback = os.environ.get("ENCRYPTION_KEY_FALLBACK", "").strip()
    missing = []
    if not primary:
        missing.append("ENCRYPTION_KEY_PRIMARY")
    if not fallback:
        missing.append("ENCRYPTION_KEY_FALLBACK")
    if missing:
        raise RuntimeError(
            "\n[secrets_manager] Missing environment variables: " + ", ".join(missing) + "\n"
            "  Local dev  : add them to your .env file\n"
            "  GitHub CI  : add them as repo secrets\n"
        )
    return primary.encode(), fallback.encode()


# ── Vault loading ─────────────────────────────────────────────────────────────

def _load_vault() -> dict:
    for candidate in [Path(__file__).with_name("secrets.enc"), Path("secrets.enc")]:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        "\n[secrets_manager] secrets.enc not found.\n"
        "  Run: python generate_secrets.py\n"
    )


# ── Decryption ────────────────────────────────────────────────────────────────

def _double_decrypt(ciphertext: str, primary: bytes, fallback: bytes) -> str:
    """Fernet(FALLBACK).decrypt(Fernet(PRIMARY).decrypt(ciphertext))"""
    try:
        inner = Fernet(primary).decrypt(ciphertext.encode())
        return Fernet(fallback).decrypt(inner).decode()
    except InvalidToken:
        raise RuntimeError(
            "\n[secrets_manager] Decryption failed — wrong keys or corrupted secrets.enc.\n"
            "  Check ENCRYPTION_KEY_PRIMARY and ENCRYPTION_KEY_FALLBACK.\n"
        )


def _audit(name: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    caller = "unknown"
    try:
        import inspect
        frame = inspect.stack()[2]
        caller = f"{Path(frame.filename).name}:{frame.lineno}"
    except Exception:
        pass
    logging.getLogger(__name__).debug("[secrets] get_secret(%r) called by %s at %s", name, caller, ts)


# ── Public API ────────────────────────────────────────────────────────────────

def get_secret(name: str) -> str:
    """Decrypt and return a single secret. Logs caller + timestamp (not the value)."""
    global _sanitizer_installed
    if not _sanitizer_installed:
        _install_sanitizer()
        _sanitizer_installed = True

    primary, fallback = _get_keys()
    vault = _load_vault()
    if name not in vault:
        raise KeyError(
            f"\n[secrets_manager] Secret '{name}' not in secrets.enc.\n"
            f"  Available: {list(vault.keys())}\n"
        )
    _audit(name)
    value = _double_decrypt(vault[name], primary, fallback)
    SecretSanitizer.register(value)
    return value


def get_all_secrets() -> dict:
    """Decrypt all secrets and return as plain dict."""
    global _sanitizer_installed
    if not _sanitizer_installed:
        _install_sanitizer()
        _sanitizer_installed = True

    primary, fallback = _get_keys()
    vault = _load_vault()
    result = {}
    for name, ciphertext in vault.items():
        value = _double_decrypt(ciphertext, primary, fallback)
        SecretSanitizer.register(value)
        result[name] = value
    return result


def inject_to_env() -> None:
    """Decrypt all secrets and inject into os.environ for this process."""
    for name, value in get_all_secrets().items():
        os.environ[name] = value
