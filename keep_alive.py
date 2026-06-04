"""
keep_alive.py — Autoscale-optimised self-pinger.

Strategy for Replit Autoscale (no Reserved VM):
  • Initial burst: ping at t=10s and t=30s so the server is warm immediately.
  • Steady-state: ping every 90 seconds — well under the ~5-min idle threshold
    at which Autoscale may spin down an instance.
  • Each failed ping is logged but never crashes the loop.
"""
import time, requests, os, logging

log = logging.getLogger(__name__)

PORT         = int(os.environ.get("PORT", 8080))
PING_URL     = f"http://127.0.0.1:{PORT}/"
PING_INTERVAL = 90   # seconds — aggressive enough to prevent Autoscale idle-down


def keep_alive():
    """Ping the local server on a burst-then-steady schedule."""
    log.info(f"Keep-alive started — target: {PING_URL} | interval: {PING_INTERVAL}s")

    # Burst phase: two quick pings while server finishes full startup
    for delay in (10, 30):
        time.sleep(delay if delay == 10 else 20)   # 10s, then another 20s = 30s total
        _ping("burst")

    # Steady-state loop
    while True:
        time.sleep(PING_INTERVAL)
        _ping("steady")


def _ping(phase: str):
    try:
        r = requests.get(PING_URL, timeout=10)
        log.info(f"Keep-alive [{phase}] ping OK — HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"Keep-alive [{phase}] ping failed: {e}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("system.log"),
            logging.StreamHandler()
        ]
    )
    keep_alive()
