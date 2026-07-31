"""
v6_crypto.py — V6 Master Pro | API Key Encryption (P0)
Fernet symmetric encryption. Key derived from SECRET_KEY env var.
"""
import os, base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT = b"v6-master-pro-salt-v1"

def _get_fernet() -> Fernet:
    secret = (os.getenv("SECRET_KEY", "786") or "786").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret))
    return Fernet(key)

def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()

def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""
