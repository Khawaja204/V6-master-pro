with open("main.py", "r") as f:
    content = f.read()

# Find the _API_KEYS loading section and add env fallback
old_block = '''if not _API_KEYS:
    try:
        with open(_API_KEYS_FILE) as _f:
            _raw_keys = json.load(_f)'''

new_block = '''# ── RENDER FREE TIER FIX: read API keys from env vars (persistent) ──
if not _API_KEYS:
    _env_key = os.getenv("BINANCE_API_KEY", "").strip()
    _env_sec = os.getenv("BINANCE_SECRET_KEY", "").strip()
    if _env_key and _env_sec:
        _API_KEYS["BINANCE"] = {
            "api_key": _env_key,
            "secret_key": _env_sec,
        }
        print("[RENDER] Binance API keys loaded from environment variables.")

if not _API_KEYS:
    try:
        with open(_API_KEYS_FILE) as _f:
            _raw_keys = json.load(_f)'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("main.py", "w") as f:
        f.write(content)
    print("✅ main.py patched: env var API key fallback added")
else:
    print("⚠️ Could not find insertion point. Please share main.py around line 170.")
