"""Tiny cached HTTP helper (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "gspro-replay/1.0 (personal golf round visualiser)"
CACHE = Path(os.environ.get("GSPRO_REPLAY_CACHE", Path.home() / ".cache" / "gspro-replay"))


def _cache_path(url, data):
    h = hashlib.sha1((url + "|" + (data or "")).encode()).hexdigest()
    return CACHE / h[:2] / h


def fetch(url, params=None, data=None, cache=True, retries=3, timeout=120, quiet=False) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    cp = _cache_path(url, data)
    if cache and cp.exists():
        return cp.read_bytes()
    body = data.encode() if isinstance(data, str) else data
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = r.read()
            if cache:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_bytes(out)
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            if not quiet:
                print(f"  ! {e} ({url[:90]}...) retry {attempt + 1}/{retries}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Download failed: {url}\n{last}")


def fetch_json(url, params=None, data=None, cache=True):
    return json.loads(fetch(url, params=params, data=data, cache=cache).decode("utf-8"))


def download_file(url, dest: Path, quiet=False, tries=6):
    """Stream a (possibly large) file to disk, skipping if present.
    Retries politely on 429/5xx (honouring Retry-After) and dropped connections."""
    import urllib.error
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total and not quiet:
                        print(f"\r  {dest.name}: {got / 1e6:.0f}/{total / 1e6:.0f} MB", end="", flush=True)
            if not quiet:
                print()
            tmp.replace(dest)
            return dest
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = e.headers.get("Retry-After")
            wait = int(wait) if wait and wait.isdigit() else 20 * (attempt + 1)
            print(f"  server busy (HTTP {e.code}); waiting {wait}s before retrying {dest.name} ...")
            time.sleep(min(wait, 180))
        except (OSError, TimeoutError) as e:
            if attempt == tries - 1:
                raise
            print(f"  download interrupted ({e}); retrying {dest.name} ...")
            time.sleep(10 * (attempt + 1))
    return dest
