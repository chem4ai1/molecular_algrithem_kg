#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the table of contents of README.md in place.

The TOC is written between the ``<!-- START_TOC -->`` and ``<!-- END_TOC -->``
markers. GitHub anchors are built with the same rules GitHub itself uses:
lower case, drop everything that is not a letter, digit, hyphen, underscore or
space (unicode aware), then replace spaces with hyphens.

Usage:
    python scripts/generate_toc.py            # update README.md
    python scripts/generate_toc.py --check    # exit 1 when TOC is outdated
    python scripts/generate_toc.py --file X.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_README = REPO_ROOT / "README.md"

START = "<!-- START_TOC -->"
END = "<!-- END_TOC -->"
HEADING = re.compile(r"^(#{2,3})\s+(.*?)\s*$", re.MULTILINE)
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def slugify(text: str) -> str:
    """Convert a heading to a GitHub compatible anchor."""
    text = text.strip().lower()
    # GitHub keeps word characters (unicode aware), hyphens, underscores, spaces.
    text = re.sub(r"[^\w\- ]+", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def strip_code(text: str) -> str:
    """Blank out fenced code blocks so headings inside them are ignored."""
    def blank(match: re.Match[str]) -> str:
        return "\n".join("" for _ in match.group(0).splitlines())

    return FENCE.sub(blank, text)


def build_toc(content: str) -> str:
    lines = []
    for hashes, title in HEADING.findall(strip_code(content)):
        level = len(hashes)
        if level == 2:
            lines.append(f"- [{title}](#{slugify(title)})")
        else:  # level == 3
            lines.append(f"  - [{title}](#{slugify(title)})")
    return "\n".join(lines)


def render(content: str) -> str:
    toc = build_toc(content)
    if START not in content or END not in content:
        raise SystemExit(f"markers {START} / {END} not found in file")
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END), re.DOTALL
    )
    return pattern.sub(f"{START}\n\n{toc}\n\n{END}", content, count=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(DEFAULT_README), help="markdown file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write, exit with code 1 when the TOC is outdated",
    )
    args = parser.parse_args()

    path = Path(args.file)
    original = path.read_text(encoding="utf-8")
    updated = render(original)

    if args.check:
        if original == updated:
            print("TOC is up to date.")
            return 0
        print("TOC is outdated, run: python scripts/generate_toc.py")
        return 1

    if original == updated:
        print("TOC already up to date, nothing written.")
        return 0

    path.write_text(updated, encoding="utf-8")
    entries = build_toc(updated).count("\n") + 1
    print(f"TOC updated with {entries} entries in {path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
