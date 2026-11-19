#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the Markdown sources consumed by MkDocs.

The list itself lives in README.md. This script copies it (and the community
documents) into ``docs/`` while rewriting repository relative links so that
they still resolve inside the site, and strips the hand maintained table of
contents because MkDocs renders its own sidebar.

Usage:
    python scripts/build_site.py          # regenerate docs/
    python scripts/build_site.py --check  # exit 1 when docs/ is stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
REPO_URL = "https://github.com/awesome-ontology/awesome-ontology"

START_TOC = "<!-- START_TOC -->"
END_TOC = "<!-- END_TOC -->"

# Repository files that become site pages.
COPIES = {
    "CONTRIBUTING.md": "contributing.md",
    "CODE_OF_CONDUCT.md": "code-of-conduct.md",
    "scripts/README.md": "maintenance.md",
}

# Links that only make sense inside the repository and have to be rewritten.
LINK_REWRITES = {
    "](CONTRIBUTING.md)": "](contributing.md)",
    "](CODE_OF_CONDUCT.md)": "](code-of-conduct.md)",
    "](docs/research_plan_awesome_ontology.md)": "](research_plan_awesome_ontology.md)",
    "](docs/research_report_awesome_ontology.md)": "](research_report_awesome_ontology.md)",
    "](scripts/README.md)": "](maintenance.md)",
    "](LICENSE)": f"]({REPO_URL}/blob/main/LICENSE)",
}


def render_readme(text: str) -> str:
    """Drop the generated TOC block and rewrite repository relative links."""
    if START_TOC in text and END_TOC in text:
        pattern = re.compile(re.escape(START_TOC) + r".*?" + re.escape(END_TOC), re.DOTALL)
        text = pattern.sub("", text, count=1)
        # Remove the blank lines the markers left behind.
        text = re.sub(r"\n{3,}", "\n\n", text)

    for old, new in LINK_REWRITES.items():
        text = text.replace(old, new)
    return text.strip() + "\n"


def build() -> dict[Path, str]:
    """Return the desired content of every generated page."""
    pages: dict[Path, str] = {DOCS_DIR / "index.md": render_readme((REPO_ROOT / "README.md").read_text(encoding="utf-8"))}

    for source, target in COPIES.items():
        content = (REPO_ROOT / source).read_text(encoding="utf-8")
        for old, new in LINK_REWRITES.items():
            content = content.replace(old, new)
        pages[DOCS_DIR / target] = content.strip() + "\n"

    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write, exit with code 1 when docs/ is out of date",
    )
    args = parser.parse_args()

    pages = build()

    if args.check:
        stale = [
            path.name
            for path, content in pages.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print("docs/ is out of date, run: python scripts/build_site.py")
            print(f"  stale: {', '.join(stale)}")
            return 1
        print("docs/ is up to date.")
        return 0

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in pages.items():
        path.write_text(content, encoding="utf-8")
    print(f"generated {len(pages)} pages in {DOCS_DIR}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
