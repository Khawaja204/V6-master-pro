import functools
import sys
from flask import Blueprint

def _main():
    return sys.modules.get("main") or sys.modules.get("__main__")

def _sync_main_state(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        m=_main()
        if m is None: raise RuntimeError("main module is not loaded")
        for k,v in vars(m).items():
            if k not in _LOCAL_NAMES and k not in {"bp", "wrapped", "fn"}: globals()[k]=v
        return fn(*args, **kwargs)
    return wrapped

def _admin_required_proxy(fn):
    return _main()._admin_required(fn)

def _limiter_limit(rule):
    return _main().limiter.limit(rule)

_LOCAL_NAMES = {'client_logout', 'client_portal', 'client_login'}
bp = Blueprint("client", __name__)

@bp.route("/client/login", methods=["GET", "POST"])
@_limiter_limit("10 per minute")
@_sync_main_state
def client_login():
    ip = request.remote_addr
    if _check_lockout(ip): return render_template("client_login.html", error="⛔ Too many attempts.")
    error = None
    if request.method == "POST":
        user = _verify_client(request.form.get("username",""), request.form.get("password",""))
        if user and "error" not in user:
            session["client_user"] = user; session["last_active"] = time.time()
            audit(ip, "CLIENT_LOGIN", "SUCCESS", f"user={user['username']}"); return redirect("/client")
        error = user["error"] if (user and "error" in user) else "❌ Invalid credentials."
        _record_failed_login(ip)
    return render_template("client_login.html", error=error)


@bp.route("/client")
@_sync_main_state
def client_portal():
    if not session.get("client_user"): return redirect("/client/login")
    if time.time() - session.get("last_active", 0) > CONFIG["security"]["session_timeout_minutes"] * 60:
        session.clear(); return redirect("/client/login")
    session["last_active"] = time.time()
    with open("index.html", "r", encoding="utf-8") as f: return f.read()


@bp.route("/client/logout")
@_sync_main_state
def client_logout():
    session.clear(); return redirect("/client/login")

