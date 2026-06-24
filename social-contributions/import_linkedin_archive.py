#!/usr/bin/env python3
"""Import your LinkedIn data export into social-posts.jsonl.

LinkedIn lets you download your own data: Settings & Privacy -> Data Privacy ->
"Get a copy of your data" -> request the complete archive (the larger one that
includes your posts; the fast "Basic" export does not). When it's ready you get a
ZIP. Unzip it and point this script at the unzipped folder; it pulls every kind of
post LinkedIn gives you and appends any missing ones to your local
social-posts.jsonl (append-only, de-duplicated by url):

  - Shares_*.csv            your posts and reshares-with-commentary
  - InstantReposts_*.csv    plain reposts (no commentary)
  - Articles/**/*.html      your long-form articles

Usage (PowerShell):
    # point at the unzipped export folder (recommended)
    python import_linkedin_archive.py "C:\\path\\to\\unzipped-linkedin-export"

    # or at a single CSV (Shares_*.csv or InstantReposts_*.csv)
    python import_linkedin_archive.py "C:\\path\\to\\Shares_4376753.csv"

Classification:
  - article (long-form /pulse/ post, or an Articles/*.html file)  -> "article"
  - reshare of someone else's content (Shares row has SharedUrl)  -> "repost"
  - plain repost (from InstantReposts_*.csv)                      -> "repost"
  - your own original update                                      -> "post"

Common options:
    --since / --until YYYY-MM-DD   limit the imported date range
    --out <path>                   target file (default: %USERPROFILE%\\social-posts.jsonl)
    --dry-run                      preview without writing

Standard library only. No network, no credentials -- it just reads local files.
"""
from __future__ import annotations

import argparse
import csv
import glob
import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _pacific_offset_hours(d: date) -> int:
    """US Pacific UTC offset: -7 during DST (2nd Sun Mar .. 1st Sun Nov), else -8."""
    dst_start = _nth_weekday(d.year, 3, 6, 2)
    dst_end = _nth_weekday(d.year, 11, 6, 1)
    return -7 if (dst_start <= d < dst_end) else -8


def _to_local_date(raw: str) -> str:
    """Parse a LinkedIn export date string into a Pacific YYYY-MM-DD."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty date")
    s = s.replace("UTC", "").strip()
    # Date-only -> use as-is (no timezone shift possible/meaningful).
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            off = _pacific_offset_hours(dt.date())
            return (dt + timedelta(hours=off)).date().isoformat()
        except ValueError:
            continue
    # Last resort: ISO 8601 with offset.
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        off = _pacific_offset_hours(dt.date())
        return (dt + timedelta(hours=off)).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"unrecognized date: {raw!r}") from exc


def _clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:80]


def _existing_urls(out_path: str) -> set:
    urls = set()
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    urls.add(json.loads(line).get("url"))
                except json.JSONDecodeError:
                    continue
    return urls


def _pick(row: dict, *names: str) -> str:
    """Case-insensitive column lookup tolerant of LinkedIn's header variants."""
    lower = {k.strip().lower(): (v or "") for k, v in row.items() if k}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()].strip()
    return ""


def _classify(share_link: str, shared_url: str) -> str:
    if "/pulse/" in (share_link or "").lower():
        return "article"
    if shared_url:
        return "repost"
    return "post"


# Record tuple shape used internally: (raw_date, ptype, url, title)

def _iter_shares(path: str):
    """Yield records from a Shares_*.csv (posts and reshares-with-commentary)."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            share_link = _pick(row, "ShareLink", "Share Link", "Link", "Url")
            shared_url = _pick(row, "SharedUrl", "Shared Url", "SharedURL")
            commentary = _pick(row, "ShareCommentary", "Share Commentary", "Commentary")
            raw_date = _pick(row, "Date", "Created Date", "Share Date")
            if not share_link:
                continue
            yield raw_date, _classify(share_link, shared_url), share_link, commentary


def _iter_reposts(path: str):
    """Yield records from an InstantReposts_*.csv (plain reposts -> 'repost')."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            link = _pick(row, "Link", "ShareLink", "Url")
            raw_date = _pick(row, "Date", "Created Date")
            if not link:
                continue
            yield raw_date, "repost", link, ""


_ART_LINK_RE = re.compile(r"<h1>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_ART_DATE_RE = re.compile(r"class=\"published\">\s*Published on\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def _iter_articles(dirpath: str):
    """Yield records from Articles/**/*.html (long-form articles -> 'article')."""
    for root, _dirs, files in os.walk(dirpath):
        for name in sorted(files):
            if not name.lower().endswith((".html", ".htm")):
                continue
            with open(os.path.join(root, name), "r", encoding="utf-8", errors="replace") as fh:
                doc = fh.read()
            link = _ART_LINK_RE.search(doc)
            dm = _ART_DATE_RE.search(doc)
            if not link or not dm:
                continue
            url = link.group(1).strip()
            title = html.unescape(re.sub(r"<[^>]+>", "", link.group(2)))
            yield dm.group(1), "article", url, title


def _discover(path: str):
    """Yield (raw_date, ptype, url, title) from a LinkedIn export folder or single CSV."""
    if os.path.isdir(path):
        for fn in sorted(glob.glob(os.path.join(path, "Shares*.csv"))):
            yield from _iter_shares(fn)
        for fn in sorted(glob.glob(os.path.join(path, "InstantReposts*.csv"))):
            yield from _iter_reposts(fn)
        art_dir = os.path.join(path, "Articles")
        if os.path.isdir(art_dir):
            yield from _iter_articles(art_dir)
        return
    base = os.path.basename(path).lower()
    if base.startswith("instantreposts"):
        yield from _iter_reposts(path)
    else:
        yield from _iter_shares(path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Import a LinkedIn data export into social-posts.jsonl")
    p.add_argument("export_path", help="Path to your unzipped LinkedIn export folder (or a single Shares_*.csv / InstantReposts_*.csv)")
    default_out = os.path.join(os.path.expanduser("~"), "social-posts.jsonl")
    p.add_argument("--out", default=default_out, help=f"Target jsonl (default: {default_out})")
    p.add_argument("--since", help="Only import posts on/after this YYYY-MM-DD")
    p.add_argument("--until", help="Only import posts on/before this YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args(argv)

    if not os.path.exists(args.export_path):
        print(f"ERROR: path not found: {args.export_path}", file=sys.stderr)
        return 2

    existing = _existing_urls(args.out)
    seen = set()
    new_lines = []
    counts = {"post": 0, "article": 0, "repost": 0}
    skipped_window = skipped_dup = skipped_nourl = 0
    rows = 0

    for raw_date, ptype, url, title in _discover(args.export_path):
        rows += 1
        url = (url or "").strip()
        if not url:
            skipped_nourl += 1
            continue
        try:
            d = _to_local_date(raw_date)
        except ValueError:
            skipped_nourl += 1
            continue

        if args.since and d < args.since:
            skipped_window += 1
            continue
        if args.until and d > args.until:
            skipped_window += 1
            continue

        if url in existing or url in seen:
            skipped_dup += 1
            continue
        seen.add(url)

        counts[ptype] = counts.get(ptype, 0) + 1
        rec = {
            "date": d,
            "platform": "linkedin",
            "type": ptype,
            "url": url,
            "title": _clean_title(title),
        }
        new_lines.append(json.dumps(rec, ensure_ascii=False))

    total_new = len(new_lines)
    print(f"Read {rows} rows from {args.export_path}.")
    print(f"  would add: {total_new}  (post={counts['post']}, article={counts['article']}, repost={counts['repost']})")
    print(f"  skipped: no-url/bad-date={skipped_nourl} out-of-window={skipped_window} duplicate={skipped_dup}")

    if total_new == 0:
        print("Nothing to import.")
        return 0

    if args.dry_run:
        print("\n--dry-run: not writing. Sample of new entries:")
        for line in new_lines[:5]:
            print("  " + line)
        return 0

    with open(args.out, "a", encoding="utf-8") as fh:
        for line in new_lines:
            fh.write(line + "\n")
    print(f"\nAppended {total_new} entries to {args.out}")
    print("Next: run publish.py to push, then the chart re-renders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
