#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check every http(s) link in the list for reachability.

Only the Python standard library is used, so the script runs anywhere.
Requests are issued concurrently; a URL that refuses HEAD is retried with a
ranged GET before being reported as broken.

Usage:
    python scripts/check_links.py                 # check README.md
    python scripts/check_links.py --workers 32
    python scripts/check_links.py --timeout 20 --json reports/links.json
    python scripts/check_links.py --file CONTRIBUTING.md

Exit code is 1 when at least one link is broken (unless --no-fail is given).
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_README = REPO_ROOT / "README.md"
DEFAULT_IGNORE = Path(__file__).resolve().parent / "ignore-links.txt"

LINK = re.compile(r"\((https?://[^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)

USER_AGENT = "awesome-ontology-link-checker/1.0 (+https://github.com/awesome-ontology/awesome-ontology)"

RETRY_STATUS = {403, 405, 429, 501}


class Result:
    __slots__ = ("url", "status", "error")

    def __init__(self, url: str, status: int | None, error: str | None) -> None:
        self.url = url
        self.status = status
        self.error = error

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 400

    def as_dict(self) -> dict:
        return {"url": self.url, "status": self.status, "error": self.error, "ok": self.ok}


def collect_links(path: Path) -> list[str]:
    content = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8"))
    seen: list[str] = []
    for url in LINK.findall(content):
        url = url.rstrip(".,;")
        if url not in seen:
            seen.append(url)
    return seen


def load_ignore(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def probe(url: str, timeout: float) -> Result:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return Result(url, response.status, None)
    except urllib.error.HTTPError as exc:
        if exc.code not in RETRY_STATUS:
            return Result(url, exc.code, str(exc.reason))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        head_error = str(getattr(exc, "reason", exc))
    else:
        head_error = ""  # pragma: no cover - defensive

    # Some servers reject HEAD; fall back to a small ranged GET.
    headers["Range"] = "bytes=0-1024"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return Result(url, response.status, None)
    except urllib.error.HTTPError as exc:
        return Result(url, exc.code, str(exc.reason))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return Result(url, None, f"{head_error or ''} {getattr(exc, 'reason', exc)}".strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(DEFAULT_README))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--ignore-file", default=str(DEFAULT_IGNORE))
    parser.add_argument("--json", dest="json_out", default=None, help="write a machine readable report")
    parser.add_argument("--no-fail", action="store_true", help="always exit with 0")
    args = parser.parse_args()

    path = Path(args.file)
    links = collect_links(path)
    ignore = load_ignore(Path(args.ignore_file))
    todo = [url for url in links if url not in ignore]

    print(f"checking {len(todo)} links from {path} ({len(links) - len(todo)} ignored)")
    started = time.time()
    results: list[Result] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe, url, args.timeout): url for url in todo}
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            flag = "ok  " if result.ok else "FAIL"
            detail = result.status if result.status is not None else (result.error or "unknown")
            print(f"[{index}/{len(todo)}] {flag} {result.url} -> {detail}")

    broken = [r for r in results if not r.ok]
    elapsed = time.time() - started

    print(f"\nchecked {len(results)} links in {elapsed:.1f}s, {len(broken)} broken")
    for result in sorted(broken, key=lambda r: r.url):
        print(f"  {result.url}  status={result.status}  error={result.error}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"report written to {out}")

    if broken and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
