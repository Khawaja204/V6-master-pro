---
name: GitHub connector write pacing
description: Durable guidance for syncing larger repositories through the connected GitHub proxy.
---

Bulk GitHub Git-Database writes must be throttled because the Replit connector proxy enforces a request-rate limit below the provider's normal API quota.

**Why:** Parallel blob creation exceeded the connector's 10-requests-per-second limit before a commit was created.

**How to apply:** For repository synchronization, create blobs serially or with very low concurrency, add a short delay between requests, retry rate-limited responses with backoff, then create one tree, commit, and ref update. Preserve remote-only files unless deletion is explicitly requested.