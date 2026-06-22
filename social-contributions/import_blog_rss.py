#!/usr/bin/env python3
"""Import blog posts from one or more RSS/Atom feeds into social-posts.jsonl.

RSS is the machine-readable interface a blog publishes for exactly this purpose, so
this just fetches the public feed(s) you point it at and appends any missing posts to
your local social-posts.jsonl (append-only, de-duplicated by url).

Usage (PowerShell):
    python import_blog_rss.py https://devblogs.microsoft.com/author/<you>/feed/
    python import_blog_rss.py FEED1 FEED2 ...

Each item becomes:  platform "blog", type "post", date = pubDate in your local
(Pacific) calendar, url = item link, title = item title.

Common options:
    --since / --until YYYY-MM-DD   limit the imported date range
    --author NAME                  only keep items whose author/creator matches
                                   (case-insensitive substring) -- handy for shared feeds
    --platform NAME                override platform label (default: blog)
    --out <path>                   target file (default: %USERPROFILE%\\social-posts.jsonl)
    --dry-run                      preview without writing

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _pacific_offset_hours(d: date) -> int:
    """US Pacific UTC offset: -7 during DST (2nd Sun Mar .. 1st Sun Nov), else -8."""
    dst_start = _nth_weekday(d.year, 3, 6, 2)
    dst_end = _nth_weekday(d.year, 11, 6, 1)
    return -7 if (dst_start <= d < dst_end) else -8


def _to_local_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    off = _pacific_offset_hours(dt.date())
    return (dt + timedelta(hours=off)).date().isoformat()


def _parse_date(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    # RSS uses RFC-822 (Mon, 02 Jun 2025 17:30:00 +0000).
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt
    except (TypeError, ValueError):
        pass
    # Atom uses ISO-8601 (2025-06-02T17:30:00Z).
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _find_text(item: ET.Element, *names: str) -> str:
    wanted = {n.lower() for n in names}
    for child in item:
        if _localname(child.tag) in wanted and (child.text or "").strip():
            return child.text.strip()
    return ""


def _find_link(item: ET.Element) -> str:
    # RSS: <link>text</link>. Atom: <link href="..." rel="alternate"/>.
    alt = ""
    for child in item:
        if _localname(child.tag) != "link":
            continue
        if (child.text or "").strip():
            return child.text.strip()
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate").strip().lower()
        if href and rel == "alternate":
            return href
        if href and not alt:
            alt = href
    return alt


def _find_author(item: ET.Element) -> str:
    # dc:creator, <author> (RSS email or Atom <author><name>).
    for child in item:
        ln = _localname(child.tag)
        if ln == "creator" and (child.text or "").strip():
            return child.text.strip()
        if ln == "author":
            if (child.text or "").strip():
                return child.text.strip()
            name = _find_text(child, "name")
            if name:
                return name
    return ""


def _iter_items(root: ET.Element):
    for el in root.iter():
        if _localname(el.tag) in ("item", "entry"):
            yield el


def _fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "social-contributions-rss-importer/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


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
    p = argparse.ArgumentParser(description="Import blog posts from RSS/Atom feeds into social-posts.jsonl")
    p.add_argument("feeds", nargs="+", help="One or more RSS/Atom feed URLs")
    default_out = os.path.join(os.path.expanduser("~"), "social-posts.jsonl")
    p.add_argument("--out", default=default_out, help=f"Target jsonl (default: {default_out})")
    p.add_argument("--since", help="Only import posts on/after this YYYY-MM-DD")
    p.add_argument("--until", help="Only import posts on/before this YYYY-MM-DD")
    p.add_argument("--author", help="Only keep items whose author matches (case-insensitive substring)")
    p.add_argument("--platform", default="blog", help="Platform label (default: blog)")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args(argv)

    existing = _existing_urls(args.out)
    seen = set()
    new_lines = []
    skipped_window = skipped_dup = skipped_nourl = skipped_author = 0
    items_total = 0

    for feed in args.feeds:
        try:
            data = _fetch(feed)
        except Exception as exc:  # noqa: BLE001 -- report and continue with other feeds
            print(f"WARN: could not fetch {feed}: {exc}", file=sys.stderr)
            continue
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            print(f"WARN: could not parse {feed}: {exc}", file=sys.stderr)
            continue

        for item in _iter_items(root):
            items_total += 1
            url = _find_link(item)
            if not url:
                skipped_nourl += 1
                continue
            if args.author:
                author = _find_author(item)
                if args.author.lower() not in author.lower():
                    skipped_author += 1
                    continue
            dt = _parse_date(_find_text(item, "pubDate", "published", "updated", "date"))
            if dt is None:
                skipped_nourl += 1
                continue
            d = _to_local_date(dt)
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
            rec = {
                "date": d,
                "platform": args.platform,
                "type": "post",
                "url": url,
                "title": _find_text(item, "title")[:80],
            }
            new_lines.append(json.dumps(rec, ensure_ascii=False))

    total_new = len(new_lines)
    print(f"Scanned {items_total} feed items from {len(args.feeds)} feed(s).")
    print(f"  would add: {total_new}")
    print(f"  skipped: no-url/bad-date={skipped_nourl} out-of-window={skipped_window} duplicate={skipped_dup} author-filter={skipped_author}")

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
