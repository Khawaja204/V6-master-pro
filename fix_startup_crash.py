with open("main.py", "r") as f:
    content = f.read()

safe_startup_block = '''
# --- Safe Startup Telegram Notification ---
try:
    _bn_status = "❌ DISCONNECTED"
    try:
        from logic import ping_binance
        if ping_binance():
            _bn_status = "✅ CONNECTED"
    except Exception as _e:
        print(f"[STARTUP] Ping Binance check skipped: {_e}")

    _mode = "PAPER" if GLOBAL_DATA.get('paper_mode', True) else "REAL" if 'GLOBAL_DATA' in globals() else "PAPER"
    _port = os.getenv("PORT", "5000")
    
    send_telegram(
        f"🚀 <b>V6 MASTER PRO v8 ONLINE</b>\\n\\n"
        f"PORT:{_port} | Exchange:BINANCE\\n\\n"
        f"🎯 FocusMode✅ CandlestickChart✅ WhalePanels✅\\n"
        f"🤖 Bot:/sniper /winrate /status\\n\\n"
        f"🔑 Binance API: {_bn_status}\\n"
        f"📄 Mode: {_mode}\\n"
        f"Admin:/admin | Client:/client | Focus:/focus"
    )
except Exception as _err:
    print(f"[STARTUP] Telegram startup alert bypassed due to error: {_err}")
'''

import re
pattern = r'# --- Binance connectivity check on startup ---.*?send_telegram\(.*?\)'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, safe_startup_block.strip(), content, flags=re.DOTALL)
    with open("main.py", "w") as f:
        f.write(content)
    print("✅ Main.py patched successfully!")
else:
    print("⚠️ Pattern match not found, writing wrapper patch.")
