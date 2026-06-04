import time, requests, os, logging

log = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8080))

def keep_alive():
    """Pings the local server every 300 seconds to prevent sleep."""
    url = f"http://127.0.0.1:{PORT}/"
    time.sleep(30)  # Let the server fully start before first ping
    log.info(f"Keep-alive started — pinging {url} every 300s")
    while True:
        try:
            r = requests.get(url, timeout=10)
            log.info(f"Keep-alive ping OK: {r.status_code}")
        except Exception as e:
            log.warning(f"Keep-alive ping failed: {e}")
        time.sleep(300)

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
