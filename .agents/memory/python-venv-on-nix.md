---
name: Python venv on Nix
description: Avoid PEP 668 failures when installing Python packages in this Nix-based workspace.
---

Python package installation through the Replit package installer can target the immutable Nix interpreter and fail with `externally-managed-environment`. Use `uv venv` to create `.venv`, then `uv pip install --python .venv/bin/python -r requirements.txt`; never bypass the protection with `--break-system-packages`.

**Why:** The workspace's Python base module has no pip module and its interpreter lives in `/nix/store`; a package-install attempt failed with PEP 668. A local uv-managed virtual environment installed the pinned dependencies successfully.

**How to apply:** For Python packages in this workspace, use `scripts/setup-python-venv.sh` and keep `.venv` excluded from Git and deployment bundles. The trading terminal's production build remains Pnpm-based and does not need Python dependencies.
