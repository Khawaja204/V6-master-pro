---
name: Binance connectivity resilience
description: How the data layer survives transient DNS/network failures to Binance and how connection health is reported.
---

# Binance connectivity resilience

On Replit, `api.binance.com` occasionally throws transient DNS failures
(`HTTPSConnectionPool: Failed to resolve api.binance.com`) even though the host
is reachable seconds later. A single bare `requests.get` against one host
surfaces these blips as hard errors.

**Pattern used (logic.py):**
- A shared `requests.Session` with a `urllib3` Retry adapter (connect/read
  retries + backoff, retry on 429/5xx).
- `_binance_get(path)` iterates an ordered `BINANCE_HOSTS` list
  (api / api1 / api2 / api-gcp / data-api.binance.vision) and fails over to the
  next host on connection errors AND on infra-class statuses (429/451/5xx).
- Returns None when every host fails; all callers must guard `if resp is None`.

**Health reporting rule:** connection status must reflect *real reachability*,
not credential/key presence. A green indicator from "keys exist" lies when the
network is down.
**Why:** the architect flagged that marking healthy on any HTTP response (incl.
4xx/5xx) or reporting "configured" as "connected" gives false-green status.
**How to apply:** mark reachable only on a usable response (2xx or normal 4xx
like bad-symbol); a dedicated background thread (`start_health_monitor`) probes
every 30s and updates a locked snapshot. `/system_health` returns the snapshot
only — never do network work in that request path (it's public → DoS amplifier).
