#!/usr/bin/env python3
"""Poll a health endpoint until 2xx or timeout. Replaces brittle `sleep N`.

Emits per-attempt timing to stderr (job-summary friendly). Exits 0 on first
successful response, 1 on timeout or after --max-failures consecutive failures.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True, help="URL to GET; success is any 2xx response")
    p.add_argument("--timeout", type=float, default=60.0, help="Total timeout in seconds (default: 60)")
    p.add_argument("--interval", type=float, default=2.0, help="Seconds between attempts (default: 2)")
    p.add_argument(
        "--max-failures",
        type=int,
        default=0,
        help="Bail early after N consecutive failures (default: 0 = honor --timeout only)",
    )
    p.add_argument("--per-request-timeout", type=float, default=5.0, help="Per-request socket timeout (default: 5s)")
    return p.parse_args()


def attempt(url: str, per_request_timeout: float) -> tuple[bool, str]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=per_request_timeout) as resp:
            elapsed = (time.monotonic() - started) * 1000
            ok = 200 <= resp.status < 300
            return ok, f"{resp.status} in {elapsed:.0f}ms"
    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - started) * 1000
        return False, f"HTTP {e.code} in {elapsed:.0f}ms"
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        elapsed = (time.monotonic() - started) * 1000
        return False, f"{type(e).__name__}: {e} in {elapsed:.0f}ms"


def main() -> int:
    args = parse_args()
    deadline = time.monotonic() + args.timeout
    consecutive_failures = 0
    attempts = 0

    while time.monotonic() < deadline:
        attempts += 1
        ok, detail = attempt(args.url, args.per_request_timeout)
        sys.stderr.write(f"wait_for_health[{attempts}]: {args.url} -> {detail}\n")
        sys.stderr.flush()

        if ok:
            sys.stderr.write(f"wait_for_health: healthy after {attempts} attempt(s)\n")
            return 0

        consecutive_failures += 1
        if args.max_failures and consecutive_failures >= args.max_failures:
            sys.stderr.write(f"wait_for_health: bailing after {consecutive_failures} consecutive failures\n")
            return 1

        time.sleep(args.interval)

    sys.stderr.write(f"wait_for_health: timed out after {args.timeout}s ({attempts} attempts)\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
