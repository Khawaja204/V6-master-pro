with open("main.py", "r") as f:
    content = f.read()

old_send = '''    send_telegram(
        f"🚀 <b>V6 MASTER PRO v8 ONLINE</b>\\n"
        f"PORT:{PORT} | Exchange:BINANCE\\n"
        f"🎯 FocusMode✅ CandlestickChart✅ WhalePanels✅\\n"
        f"🤖 Bot:/sniper /winrate /status ✅\\n"
        f"Admin:/admin | Client:/client | Focus:/focus"
    )'''

new_send = '''    # ── Binance connectivity check on startup ──
    _bn_status = "❌ DISCONNECTED"
    try:
        from logic import ping_binance
        if ping_binance():
            _bn_status = "✅ CONNECTED"
    except Exception:
        pass
    send_telegram(
        f"🚀 <b>V6 MASTER PRO v8 ONLINE</b>\\n"
        f"PORT:{PORT} | Exchange:BINANCE\\n"
        f"🎯 FocusMode✅ CandlestickChart✅ WhalePanels✅\\n"
        f"🤖 Bot:/sniper /winrate /status ✅\\n"
        f"🔑 Binance API: {_bn_status}\\n"
        f"📄 Mode: {'PAPER' if GLOBAL_DATA.get('paper_mode',True) else 'REAL'}\\n"
        f"Admin:/admin | Client:/client | Focus:/focus"
    )'''

if old_send in content:
    content = content.replace(old_send, new_send)
    with open("main.py", "w") as f:
        f.write(content)
    print("✅ Startup Telegram message patched with Binance status")
else:
    print("⚠️ Startup block not found — skipping")
