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
SAMPLE_ROWS = 15        # rows shown in the top-of-README sample table

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
                u=j.get("url", "https://forgeapply.com"),
            )
        )
    return "\n".join(lines)


def render(sections: list[tuple[str, list[dict]]]) -> str:
    now = datetime.now(timezone.utc)
    total = sum(len(jobs) for _, jobs in sections)

    # Newest-across-both-sections sample for the top of the README. Each
    # section's jobs are already newest-first, so a simple merge by
    # posted_at (falling back to insertion order when missing) is enough.
    combined = sorted(
        (j for _, jobs in sections for j in jobs),
        key=lambda j: j.get("posted_at") or "",
        reverse=True,
    )
    sample = combined[:SAMPLE_ROWS]

    toc = " · ".join(
        f"[{label} ({len(jobs)})](#{label.lower().replace(' ', '-')})" for label, jobs in sections
    )

    parts = [
        "# Tech Jobs With Salaries",
        "",
        "Live tech roles at startups and tech companies — early-career and senior — where the employer "
        "disclosed pay. Pulled daily from the job boards startups actually hire through. No salary listed, "
        "not on this list.",
        "",
        f"**Last updated:** {now:%Y-%m-%d} (UTC) · **{total} roles** · updates daily via GitHub Actions",
        "",
        f"### Sample ({len(sample)} of {total})",
        "",
        table(sample),
        "",
        f"Full current list (same {total} roles, refreshed daily) is further down this page, split by career "
        f"stage: {toc}.",
        "",
        "## How to contribute",
        "",
        "This list is generated, not hand-edited — see [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR "
        "against the tables. The two useful contributions:",
        "",
        "- **Dead link or expired role?** [Open an issue](../../issues) with the company and role name.",
        "- **Non-tech role slipped through the filter?** Open an issue, or send a PR adding a pattern to the "
        "`NON_TECH` regex in `scripts/generate_readme.py`.",
        "",
        "## Who makes this",
        "",
        "Maintained by [ForgeApply](https://forgeapply.com), which tailors resumes and autofills job "
        "applications. This repo is just the public data feed behind that — no sign-up needed to use the list.",
        "",
    ]
    for label, jobs in sections:
        parts += [f"## {label}", "", table(jobs), ""]
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
