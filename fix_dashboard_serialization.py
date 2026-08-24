import sys, ast

PATH = 'main.py'
with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = '''@app.route("/dashboard_data")
def dashboard_data():
    try:
        return jsonify(GLOBAL_DATA)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log.error(f"[dashboard_data] serialization crash:\\n{tb}")
        return f"<pre>{tb}</pre>", 500'''

NEW = '''@app.route("/dashboard_data")
def dashboard_data():
    try:
        # oco_manager / ptp_manager are live internal objects used for real
        # trading (OCO brackets, partial TP) — they were never meant to be
        # sent to the frontend and aren't JSON-serializable. Exclude them
        # from the API response without touching GLOBAL_DATA itself.
        _safe_data = {k: v for k, v in GLOBAL_DATA.items() if k not in ("oco_manager", "ptp_manager")}
        return jsonify(_safe_data)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log.error(f"[dashboard_data] serialization crash:\\n{tb}")
        return f"<pre>{tb}</pre>", 500'''

if '_safe_data' in content:
    print("main.py: serialization fix already present — skipping")
else:
    cnt = content.count(OLD)
    if cnt != 1:
        print(f"FAILED - expected 1 anchor match, found {cnt}. Aborting, no changes written.")
        sys.exit(1)
    content = content.replace(OLD, NEW, 1)
    ast.parse(content)
    with open(PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("main.py: dashboard_data serialization fix applied OK, syntax-checked OK")

print("Done — oco_manager/ptp_manager excluded from JSON response. /dashboard_data should now work.")
