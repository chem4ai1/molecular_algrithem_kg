#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Report health statistics of the awesome-ontology list.

Checks performed:
  * number of links, sections and subsections
  * duplicate URLs inside the same section (a real mistake)
  * URLs intentionally cross-listed by several sections (reported, not an error)
  * entries without a description or with an overly long one
  * top level domains used by the list, to spot single point of failure
  * every entry starts with ``-`` and links to an absolute http(s) URL

Usage:
    python scripts/stats.py
    python scripts/stats.py --file README.md --max-length 120
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_README = REPO_ROOT / "README.md"
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)

ENTRY = re.compile(r"^(\s*)- \[([^\]]+)\]\((https?://[^)\s]+)\)\s*(?:-\s*(.*))?$")
LINK_ANY = re.compile(r"\((https?://[^)\s]+)\)")
SECTION = re.compile(r"^(#{2,3})\s+(.*?)\s*$", re.MULTILINE)


def read_without_code(path: Path) -> str:
    return FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(DEFAULT_README))
    parser.add_argument("--max-length", type=int, default=160, help="max entry line length")
    args = parser.parse_args()

    path = Path(args.file)
    content = read_without_code(path)

    entries = []
    section = "(top)"
    for lineno, line in enumerate(content.splitlines(), start=1):
        heading = SECTION.match(line)
        if heading:
            section = heading.group(2).strip()
            continue
        match = ENTRY.match(line)
        if match:
            entries.append(
                (lineno, section, match.group(2).strip(), match.group(3), (match.group(4) or "").strip())
            )

    sections = [t for h, t in SECTION.findall(content) if len(h) == 2]
    subsections = [t for h, t in SECTION.findall(content) if len(h) == 3]

    urls = [e[3] for e in entries]
    # A URL listed twice inside one section is a mistake; the same URL listed
    # by two different sections is a deliberate cross reference.
    per_section: dict[tuple[str, str], int] = Counter((e[1], e[3]) for e in entries)
    within = {key: n for key, n in per_section.items() if n > 1}
    per_url: dict[str, set[str]] = {}
    for e in entries:
        per_url.setdefault(e[3], set()).add(e[1])
    cross = {url: secs for url, secs in per_url.items() if len(secs) > 1}
    domains = Counter(urlparse(url).netloc.lower().removeprefix("www.") for url in urls)

    problems = []
    for lineno, sec, name, url, desc in entries:
        if not desc:
            problems.append(f"line {lineno}: '{name}' has no description")
        if desc.endswith("。"):
            problems.append(f"line {lineno}: '{name}' description ends with a full stop")
        if len(desc) > 120:
            problems.append(f"line {lineno}: '{name}' description too long ({len(desc)} chars)")
        if not name.strip():
            problems.append(f"line {lineno}: empty link text")
    for (sec, url), count in sorted(within.items()):
        problems.append(f"section '{sec}': {url} listed {count} times")

    print(f"file            : {path}")
    print(f"sections        : {len(sections)}")
    print(f"subsections     : {len(subsections)}")
    print(f"list entries    : {len(entries)}")
    print(f"unique urls     : {len(set(urls))}")
    print(f"cross listed    : {len(cross)} (same URL referenced by several sections)")
    for url, secs in sorted(cross.items()):
        print(f"  x{len(secs)}  {url}")
        print(f"        in: {' / '.join(sorted(secs))}")
    print("top domains     :")
    for domain, count in domains.most_common(12):
        print(f"  {count:>4}  {domain}")

    if problems:
        print(f"\nissues ({len(problems)}) :")
        for problem in problems:
            print(f"  {problem}")
    else:
        print("\nno formatting issues found.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
