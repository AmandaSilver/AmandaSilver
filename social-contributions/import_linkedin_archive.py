#!/usr/bin/env python3
"""Import your LinkedIn data export into social-posts.jsonl.

LinkedIn lets you download your own data: Settings & Privacy -> Data Privacy ->
"Get a copy of your data" -> pick "Posts" / the larger archive. When it's ready you
get a ZIP containing CSV files; the one with your posts/shares is typically
`Shares.csv` (columns: Date, ShareLink, ShareCommentary, SharedUrl, MediaUrl,
Visibility). This script reads that CSV and appends any missing posts to your local
social-posts.jsonl (append-only, de-duplicated by url).

Usage (PowerShell):
    python import_linkedin_archive.py "C:\\path\\to\\linkedin-export\\Shares.csv"

Classification:
  - row has a SharedUrl (you reshared someone else's content)  -> "repost"
  - ShareLink looks like a long-form article (/pulse/)         -> "article"
  - otherwise (your own original update)                       -> "post"

Common options:
    --since / --until YYYY-MM-DD   limit the imported date range
    --out <path>                   target file (default: %USERPROFILE%\\social-posts.jsonl)
    --dry-run                      preview without writing

Standard library only. No network, no credentials -- it just reads a local CSV.
"""
from __future__ import annotations

import argparse
import csv
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
    if shared_url:
        return "repost"
    if "/pulse/" in share_link.lower():
        return "article"
    return "post"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Import a LinkedIn data export (Shares.csv) into social-posts.jsonl")
    p.add_argument("csv_path", help="Path to Shares.csv from your LinkedIn data export")
    default_out = os.path.join(os.path.expanduser("~"), "social-posts.jsonl")
    p.add_argument("--out", default=default_out, help=f"Target jsonl (default: {default_out})")
    p.add_argument("--since", help="Only import posts on/after this YYYY-MM-DD")
    p.add_argument("--until", help="Only import posts on/before this YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args(argv)

    if not os.path.exists(args.csv_path):
        print(f"ERROR: file not found: {args.csv_path}", file=sys.stderr)
        return 2

    existing = _existing_urls(args.out)
    seen = set()
    new_lines = []
    counts = {"post": 0, "article": 0, "repost": 0}
    skipped_window = skipped_dup = skipped_nourl = 0
    rows = 0

    with open(args.csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows += 1
            share_link = _pick(row, "ShareLink", "Share Link", "Link", "Url")
            shared_url = _pick(row, "SharedUrl", "Shared Url", "SharedURL")
            commentary = _pick(row, "ShareCommentary", "Share Commentary", "Commentary")
            raw_date = _pick(row, "Date", "Created Date", "Share Date")

            if not share_link:
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

            url = share_link
            if url in existing or url in seen:
                skipped_dup += 1
                continue
            seen.add(url)

            ptype = _classify(share_link, shared_url)
            counts[ptype] += 1
            rec = {
                "date": d,
                "platform": "linkedin",
                "type": ptype,
                "url": url,
                "title": _clean_title(commentary),
            }
            new_lines.append(json.dumps(rec, ensure_ascii=False))

    total_new = len(new_lines)
    print(f"Read {rows} rows from {os.path.basename(args.csv_path)}.")
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
