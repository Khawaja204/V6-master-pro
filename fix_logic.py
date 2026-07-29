with open('logic.py', 'r') as f:
    content = f.read()

old = '''        # ── SL / TP levels ──────────────────────────────────────────────────
        if direction == "COPY_BUY":
            stop_loss = round(wall_price * (1 - sl_buffer_pct / 100), 8)
            target    = opposite["price_level"] if opposite else round(wall_price * (1 + tp_fallback_pct / 100), 8)
        else:
            stop_loss = round(wall_price * (1 + sl_buffer_pct / 100), 8)
            target    = opposite["price_level"] if opposite else round(wall_price * (1 - tp_fallback_pct / 100), 8)'''

new = '''        # ── SL / TP levels ──────────────────────────────────────────────────
        if direction == "COPY_BUY":
            stop_loss = round(wall_price * (1 - sl_buffer_pct / 100), 8)
            target    = opposite["price_level"] if opposite else round(wall_price * (1 + tp_fallback_pct / 100), 8)
            if target <= wall_price:
                target = round(wall_price * (1 + tp_fallback_pct / 100), 8)
        else:
            stop_loss = round(wall_price * (1 + sl_buffer_pct / 100), 8)
            target    = opposite["price_level"] if opposite else round(wall_price * (1 - tp_fallback_pct / 100), 8)
            if target >= wall_price:
                target = round(wall_price * (1 - tp_fallback_pct / 100), 8)'''

if old in content:
    content = content.replace(old, new)
    with open('logic.py', 'w') as f:
        f.write(content)
    print("✅ logic.py — target price fix applied")
else:
    print("❌ logic.py block not found (already fixed?)")
