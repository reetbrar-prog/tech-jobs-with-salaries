# Contributing

Thanks for helping keep this list useful.

## The tables are generated, not hand-edited

`README.md` is regenerated every day by `scripts/generate_readme.py` from two public JSON feeds:

- `https://forgeapply.com/api/public/early-career`
- `https://forgeapply.com/api/public/experienced`

A PR that edits the tables directly will be overwritten within a day. Instead:

- **Dead link or expired role?** [Open an issue](../../issues) with the company and role name. Stale roles are retired automatically when they disappear from the source board, usually within a day, but issues help us catch stragglers.
- **Miscategorized or non-tech role slipping through?** Open an issue, or send a PR adding a pattern to the `NON_TECH` regex in `scripts/generate_readme.py`.
- **Ideas for the format** (columns, sections, filters): issues and PRs against the script are both welcome.

## Ground rules

- Every listing must have disclosed pay. That's the point of the list; no exceptions.
- No scraped personal data, no referral-link swaps, no promotional listings.

## Running locally

```bash
python3 scripts/generate_readme.py
```

Python 3.10+, standard library only.
