#!/usr/bin/env python3
"""Import your X (Twitter) account archive into social-posts.jsonl.

Your official account archive (Settings -> "Download an archive of your data")
contains the *complete* history of your posts in `data/tweets.js`. This script reads
that file and appends any missing posts to your local social-posts.jsonl (append-only,
de-duplicated by url), so the contribution chart reflects your full year.

Usage (PowerShell):
    python import_x_archive.py "C:\\path\\to\\twitter-archive\\data\\tweets.js"

Common options:
    --until 2026-04-01     only import posts on/before this date
    --since 2025-06-21     only import posts on/after this date
    --include-replies      also count @-replies as posts (default: skipped)
    --no-retweets          skip retweets (default: retweets ARE imported)
    --dry-run              show what would be added without writing
    --out <path>           target file (default: %USERPROFILE%\\social-posts.jsonl)
    --handle <name>        your X handle for permalinks (default: amandaksilver)

This uses only the Python standard library. No network, no credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

DEFAULT_HANDLE = "amandaksilver"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the date of the n-th given weekday (Mon=0..Sun=6) in a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _pacific_offset_hours(d: date) -> int:
    """US Pacific UTC offset for a given date: -7 during DST, else -8.

    DST: 2nd Sunday of March through 1st Sunday of November (Sunday=6).
    Day-level precision is sufficient for a per-day activity chart.
    """
    dst_start = _nth_weekday(d.year, 3, 6, 2)
    dst_end = _nth_weekday(d.year, 11, 6, 1)
    return -7 if (dst_start <= d < dst_end) else -8


def _to_local_date(created_at: str) -> str:
    """Convert an X archive 'created_at' to a YYYY-MM-DD Pacific calendar date."""
    # Format example: "Wed Jun 11 20:30:00 +0000 2025"
    dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
    dt_utc = dt.astimezone(timezone.utc)
    off = _pacific_offset_hours(dt_utc.date())
    local = dt_utc + timedelta(hours=off)
    return local.date().isoformat()


def _load_archive(path: str) -> list:
    """Parse an X archive tweets.js / tweet.js file into a list of tweet dicts."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    # The file is JS: `window.YTD.tweets.part0 = [ ... ]`. Strip the assignment.
    start = raw.find("[")
    if start == -1:
        raise ValueError("Could not find a JSON array in the archive file.")
    data = json.loads(raw[start:])
    tweets = []
    for item in data:
        tw = item.get("tweet", item) if isinstance(item, dict) else None
        if isinstance(tw, dict):
            tweets.append(tw)
    return tweets


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80]


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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Import an X account archive into social-posts.jsonl")
    p.add_argument("archive", help="Path to the archive's data/tweets.js (or tweet.js) file")
    default_out = os.path.join(os.path.expanduser("~"), "social-posts.jsonl")
    p.add_argument("--out", default=default_out, help=f"Target jsonl (default: {default_out})")
    p.add_argument("--handle", default=DEFAULT_HANDLE, help="Your X handle for permalinks")
    p.add_argument("--since", help="Only import posts on/after this YYYY-MM-DD")
    p.add_argument("--until", help="Only import posts on/before this YYYY-MM-DD")
    p.add_argument("--include-replies", action="store_true", help="Count @-replies as posts")
    p.add_argument("--no-retweets", action="store_true", help="Skip retweets")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args(argv)

    if not os.path.exists(args.archive):
        print(f"ERROR: archive file not found: {args.archive}", file=sys.stderr)
        return 2

    try:
        tweets = _load_archive(args.archive)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not parse archive: {exc}", file=sys.stderr)
        return 2

    existing = _existing_urls(args.out)
    seen_this_run = set()
    new_lines = []
    counts = {"tweet": 0, "retweet": 0}
    skipped_reply = skipped_rt = skipped_window = skipped_dup = 0

    for tw in tweets:
        text = tw.get("full_text") or tw.get("text") or ""
        is_reply = bool(tw.get("in_reply_to_status_id_str") or tw.get("in_reply_to_status_id"))
        is_rt = text.startswith("RT @")

        if is_reply and not args.include_replies:
            skipped_reply += 1
            continue
        if is_rt and args.no_retweets:
            skipped_rt += 1
            continue

        created = tw.get("created_at")
        id_str = tw.get("id_str") or tw.get("id")
        if not created or not id_str:
            continue
        try:
            d = _to_local_date(created)
        except ValueError:
            continue

        if args.since and d < args.since:
            skipped_window += 1
            continue
        if args.until and d > args.until:
            skipped_window += 1
            continue

        url = f"https://x.com/{args.handle}/status/{id_str}"
        if url in existing or url in seen_this_run:
            skipped_dup += 1
            continue
        seen_this_run.add(url)

        ptype = "retweet" if is_rt else "tweet"
        counts[ptype] += 1
        rec = {
            "date": d,
            "platform": "x",
            "type": ptype,
            "url": url,
            "title": _clean_title(text),
        }
        new_lines.append(json.dumps(rec, ensure_ascii=False))

    total_new = len(new_lines)
    print(f"Parsed {len(tweets)} tweets from archive.")
    print(f"  would add: {total_new}  (tweet={counts['tweet']}, retweet={counts['retweet']})")
    print(f"  skipped: reply={skipped_reply} retweet={skipped_rt} "
          f"out-of-window={skipped_window} duplicate={skipped_dup}")

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
