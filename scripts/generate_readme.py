#!/usr/bin/env python3
"""Regenerate README.md from ForgeApply's public job feeds.

Runs daily via GitHub Actions (stdlib only, no dependencies).
Fail-safe: if either feed is unreachable or empty, the script exits
non-zero WITHOUT touching README.md, so yesterday's tables survive.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"

FEEDS = [
    ("early", "Early career and new grad", "https://forgeapply.com/api/public/early-career"),
    ("senior", "Senior and experienced", "https://forgeapply.com/api/public/experienced"),
]

MAX_ROWS = 175          # per table
MAX_PER_COMPANY = 3     # keep the tables from becoming one company's careers page

SITE = "https://forgeapply.com"

# The feeds are tech-focused, but titles from ~600 scraped boards are messy.
# Belt-and-suspenders exclusion of clearly non-tech roles.
NON_TECH = re.compile(
    r"veterinar|physician|dentist|counselor|counsellor|social work|nurse|nursing|"
    r"doula|therapist|clinical|medical assistant|recruiter|recruiting|talent |"
    r"sales rep|sales development|account executive|account manager|promoter|"
    r"loan |mortgage|cashier|barista|driver",
    re.I,
)

UA = {"User-Agent": "tech-jobs-with-salaries-bot (github.com; README generator)"}


def fetch(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    return payload.get("jobs", [])


def strip_tracking(url: str | None) -> str:
    """Drop utm_* query params so the link we publish is a clean canonical
    forgeapply.com URL, not a tracked one. See CONTRIBUTING.md / README for why."""
    if not url:
        return SITE
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(kept), parts.fragment)
    )


def age_label(posted_at: str | None) -> str:
    if not posted_at:
        return "—"
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    days = max(0, (datetime.now(timezone.utc) - dt).days)
    if days == 0:
        return "today"
    if days > 90:
        return "90d+"
    return f"{days}d"


def md_escape(s: str) -> str:
    return (s or "").replace("|", "/").strip()


def pick(jobs: list[dict]) -> list[dict]:
    """Salary required, non-tech excluded, capped per company, newest first."""
    out: list[dict] = []
    per_company: dict[str, int] = {}
    for j in jobs:  # feeds are already sorted newest-first
        if not j.get("salary"):
            continue
        title = j.get("title") or ""
        if NON_TECH.search(title):
            continue
        key = (j.get("company") or "").strip().lower()
        if per_company.get(key, 0) >= MAX_PER_COMPANY:
            continue
        per_company[key] = per_company.get(key, 0) + 1
        out.append(j)
        if len(out) >= MAX_ROWS:
            break
    return out


def table(jobs: list[dict]) -> str:
    lines = [
        "| Company | Role | Location | Salary | Age | Apply |",
        "|---|---|---|---:|---:|---|",
    ]
    for j in jobs:
        lines.append(
            "| {c} | {t} | {l} | {s} | {a} | [Apply]({u}) |".format(
                c=md_escape(j.get("company", "")),
                t=md_escape(j.get("title", "")),
                l=md_escape(j.get("location") or "—"),
                s=j.get("salary", ""),
                a=age_label(j.get("posted_at")),
                u=strip_tracking(j.get("url")),
            )
        )
    return "\n".join(lines)


def render(sections: list[tuple[str, list[dict]]]) -> str:
    now = datetime.now(timezone.utc)
    total = sum(len(jobs) for _, jobs in sections)
    toc = " · ".join(
        f"[{label} ({len(jobs)})](#{label.lower().replace(' ', '-')})" for label, jobs in sections
    )
    parts = [
        "# Tech Jobs With Salaries",
        "",
        f"**{total} live roles, every one with disclosed pay.** "
        f"Last updated **{now:%Y-%m-%d %H:%M} UTC** · regenerates daily via GitHub Actions.",
        "",
        toc,
        "",
    ]
    for label, jobs in sections:
        parts += [f"## {label}", "", table(jobs), ""]
    parts += [
        "---",
        "",
        "## How this is built",
        "",
        "- **Source:** live postings pulled from company Greenhouse, Ashby, Workday, Lever, and Workable "
        "boards — the ATSs startups and tech companies actually hire through.",
        "- **Frequency:** this file is regenerated every day by "
        "[`scripts/generate_readme.py`](scripts/generate_readme.py) via GitHub Actions, from ForgeApply's "
        "public job feeds.",
        "- **\"Disclosed salary\" means:** the employer's own posting includes a specific number or range. "
        "No range on the source posting, not on this list — no estimates, no third-party guesses.",
        "- **Filtering:** capped at 3 listings per company so no single employer dominates the table, "
        "plus a keyword filter that drops obviously non-tech roles (recruiting, sales, clinical, etc.) "
        "that slip into the source feeds.",
        "",
        f"Full search, filters, and the rest of the corpus: [forgeapply.com]({SITE}).",
        "",
        "## Contributing",
        "",
        "This file is generated — don't hand-edit the tables, they'll be overwritten within a day. "
        "Found a dead link, an expired role, or a miscategorized listing? [Open an issue](../../issues) "
        "with the company and role name. Want to fix it yourself? PRs against "
        "`scripts/generate_readme.py` (e.g. adding a pattern to `NON_TECH`) are welcome — see "
        "[CONTRIBUTING.md](CONTRIBUTING.md).",
        "",
        "## License",
        "",
        "Code in this repo is [MIT licensed](LICENSE). Job listing data is aggregated from public "
        "postings and provided as-is for personal job-search use.",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    sections: list[tuple[str, list[dict]]] = []
    for _, label, url in FEEDS:
        try:
            jobs = pick(fetch(url))
        except Exception as e:  # noqa: BLE001 - fail safe, keep old README
            print(f"feed failed ({url}): {e}", file=sys.stderr)
            return 1
        if not jobs:
            print(f"feed empty ({url}); refusing to overwrite README", file=sys.stderr)
            return 1
        sections.append((label, jobs))
    README.write_text(render(sections), encoding="utf-8")
    print(f"wrote {README} with {sum(len(j) for _, j in sections)} roles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
