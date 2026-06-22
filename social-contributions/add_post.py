#!/usr/bin/env python3
"""Append a single post to social-posts.jsonl by hand.

For the "I just posted something, add it now" case -- no export needed. It writes one
line to your local social-posts.jsonl (de-duplicated by url).

Usage (PowerShell):
    python add_post.py --platform linkedin --type post --url https://www.linkedin.com/posts/...
    python add_post.py --platform x --type retweet --url https://x.com/someone/status/123 --date 2026-06-20 --title "RT of ..."

Arguments:
    --platform   linkedin | blog | x | twitter | medium | substack | ...  (required)
    --type       post | article | repost | tweet | retweet              (required)
    --url        canonical link to the post                              (required)
    --date       YYYY-MM-DD (default: today, your local Pacific date)
    --title      short label (optional)
    --out        target file (default: %USERPROFILE%\\social-posts.jsonl)
    --dry-run    print the line without writing

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _pacific_offset_hours(d: date) -> int:
    dst_start = _nth_weekday(d.year, 3, 6, 2)
    dst_end = _nth_weekday(d.year, 11, 6, 1)
    return -7 if (dst_start <= d < dst_end) else -8


def _today_pacific() -> str:
    now = datetime.now(timezone.utc)
    off = _pacific_offset_hours(now.date())
    return (now + timedelta(hours=off)).date().isoformat()


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


VALID_TYPES = {"post", "article", "repost", "tweet", "retweet", "reshare", "share"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Append one post to social-posts.jsonl")
    p.add_argument("--platform", required=True, help="linkedin | blog | x | twitter | medium | ...")
    p.add_argument("--type", required=True, help="post | article | repost | tweet | retweet")
    p.add_argument("--url", required=True, help="Canonical link to the post")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today, Pacific)")
    p.add_argument("--title", default="", help="Short label (optional)")
    default_out = os.path.join(os.path.expanduser("~"), "social-posts.jsonl")
    p.add_argument("--out", default=default_out, help=f"Target jsonl (default: {default_out})")
    p.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = p.parse_args(argv)

    d = args.date or _today_pacific()
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got {d!r}", file=sys.stderr)
        return 2

    ptype = args.type.strip().lower()
    if ptype not in VALID_TYPES:
        print(f"WARN: unusual --type {ptype!r} (expected one of {sorted(VALID_TYPES)})", file=sys.stderr)

    rec = {
        "date": d,
        "platform": args.platform.strip().lower(),
        "type": ptype,
        "url": args.url.strip(),
        "title": args.title.strip()[:80],
    }
    line = json.dumps(rec, ensure_ascii=False)

    if rec["url"] in _existing_urls(args.out):
        print(f"Already present (same url) -- nothing added:\n  {line}")
        return 0

    if args.dry_run:
        print("--dry-run: would append:\n  " + line)
        return 0

    with open(args.out, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print("Appended:\n  " + line)
    print(f"to {args.out}\nNext: run publish.py to push, then the chart re-renders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
