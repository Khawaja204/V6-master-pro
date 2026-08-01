"""
v6_crypto.py — V6 Master Pro | API Key Encryption (at-rest)
Uses Fernet (symmetric AES-128-CBC + HMAC) from the cryptography library.
Key is derived from ENCRYPTION_KEY env var, falling back to SECRET_KEY.
"""
import os
import base64
import hashlib
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

log = logging.getLogger(__name__)

# ── Key Derivation ──
# Fernet requires a 32-byte key, base64-encoded (44 chars).
# We derive it deterministically from env vars so the same deployment
# can always decrypt its own data without storing a separate key file.

def _derive_key() -> bytes:
    """Return a Fernet-compatible key (base64-encoded 32 bytes)."""
    # Priority: ENCRYPTION_KEY > SECRET_KEY > fallback
    raw = os.getenv("ENCRYPTION_KEY", os.getenv("SECRET_KEY", "v6-master-pro-default-key"))
    # Use PBKDF2 for better key stretching if a salt is available, otherwise SHA256
    salt = os.getenv("ENCRYPTION_SALT", "v6salt786").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(raw.encode()))
    return key


# Singleton Fernet instance (lazy-loaded)
_fernet = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_derive_key())
    return _fernet


# ── Public API ──

def encrypt(plaintext: str) -> str:
    """
    Encrypt a plaintext string. Returns base64-encoded ciphertext.
    Returns empty string on failure (so callers can fall back to plaintext).
    """
    if not plaintext:
        return ""
    try:
        f = _get_fernet()
        token = f.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")
    except Exception as e:
        log.warning(f"[CRYPTO] encrypt failed: {e}")
        return ""


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a Fernet token. Returns plaintext string.
    Returns empty string on failure (callers should treat as "no valid key").
    """
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        plaintext = f.decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")
    except Exception as e:
        # Common cause: key changed (e.g. SECRET_KEY rotated) → data unreadable
        log.warning(f"[CRYPTO] decrypt failed (key mismatch or bad token): {e}")
        return ""


def rotate_key(new_key: str, old_key: str, encrypted_data: dict) -> dict:
    """
    Admin utility: re-encrypt all API keys with a new master key.
    Pass the old key to decrypt, new key to re-encrypt.
    Returns the re-encrypted dict.
    """
    import os as _os
    # Temporarily override env vars
    _os.environ["ENCRYPTION_KEY"] = old_key
    global _fernet
    _fernet = None  # force re-init with old key

    decrypted = {}
    for ex, creds in encrypted_data.items():
        decrypted[ex] = {
            "api_key": decrypt(creds.get("api_key", "")),
            "secret_key": decrypt(creds.get("secret_key", "")),
        }
        if "passphrase" in creds:
            decrypted[ex]["passphrase"] = decrypt(creds["passphrase"])

    # Switch to new key
    _os.environ["ENCRYPTION_KEY"] = new_key
    _fernet = None

    re_encrypted = {}
    for ex, creds in decrypted.items():
        re_encrypted[ex] = {
            "api_key": encrypt(creds.get("api_key", "")),
            "secret_key": encrypt(creds.get("secret_key", "")),
        }
        if "passphrase" in creds:
            re_encrypted[ex]["passphrase"] = encrypt(creds["passphrase"])

    return re_encrypted
