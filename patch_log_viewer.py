with open("main.py", "r") as f:
    content = f.read()

# Add this route before "if __name__ == '__main__':"
log_route = '''
@app.route("/admin/logs")
@_admin_required
def admin_logs():
    """Show recent logs in browser — Render free tier log alternative."""
    log_files = ["error.log", "system_audit.log"]
    output = []
    for lf in log_files:
        output.append(f"=== {lf} ===")
        try:
            with open(lf, "r") as f:
                lines = f.readlines()
            output.extend(lines[-100:])  # last 100 lines
        except Exception as e:
            output.append(f"Could not read {lf}: {e}")
        output.append("")
    return "<pre style='background:#0d1117;color:#c9d1d9;padding:20px;font-size:11px;white-space:pre-wrap'>" + "\\n".join(output) + "</pre>"

'''

insert_marker = '# ── Start Flask Server ──'
if insert_marker in content:
    content = content.replace(insert_marker, log_route + insert_marker)
    with open("main.py", "w") as f:
        f.write(content)
    print("✅ /admin/logs endpoint added")
else:
    print("⚠️ Insertion marker not found")
