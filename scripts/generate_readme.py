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


CTA_TOP = (
    "> **Tired of rewriting your resume for every posting?** "
    "[ForgeApply](https://forgeapply.com?utm_source=github&utm_medium=repo&utm_campaign=jobs_with_salaries_repo) "
    "tailors your resume to each specific job using only your real experience (it never invents anything), "
    "autofills the application, and preps you for the interview. Free 7-day trial, no card required."
)

CTA_BOTTOM = (
    "> **Applying to a few of these tonight?** The tedious part is retyping your work history into every form. "
    "[ForgeApply's extension](https://forgeapply.com?utm_source=github&utm_medium=repo&utm_campaign=jobs_with_salaries_repo) "
    "autofills applications on the job platforms startups use and attaches the resume it tailored for that exact posting."
)


def render(sections: list[tuple[str, list[dict]]]) -> str:
    now = datetime.now(timezone.utc)
    total = sum(len(jobs) for _, jobs in sections)
    toc = " · ".join(
        f"[{label} ({len(jobs)})](#{label.lower().replace(' ', '-')})" for label, jobs in sections
    )
    parts = [
        "# Tech Jobs With Salaries",
        "",
        "**Every listing here shows real, disclosed pay.** Live tech roles at startups and tech companies, "
        "pulled daily from the job boards startups actually hire through. No salary listed, not on this list.",
        "",
        f"Last updated: **{now:%Y-%m-%d}** (UTC) · {total} roles · updates daily via GitHub Actions · "
        "⭐ star this repo to check back during your search",
        "",
        toc,
        "",
        CTA_TOP,
        "",
    ]
    for label, jobs in sections:
        parts += [f"## {label}", "", table(jobs), ""]
    parts += [
        CTA_BOTTOM,
        "",
        "## About this list",
        "",
        "Maintained by [ForgeApply](https://forgeapply.com?utm_source=github&utm_medium=repo&utm_campaign=jobs_with_salaries_repo). "
        "Listings come from live postings on public startup job boards; each links to a job page with the full "
        "description, salary context for its metro, and a link to the original posting. Stale roles are retired "
        "automatically when they disappear from the source board.",
        "",
        "Found a dead link or a miscategorized role? [Open an issue](../../issues). "
        "The tables are regenerated daily, so edit `scripts/generate_readme.py`, not the tables themselves. "
        "See [CONTRIBUTING.md](CONTRIBUTING.md).",
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
