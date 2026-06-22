#!/usr/bin/env python3
"""
Social Contributions Chart generator.

Renders a GitHub-identical "contributions over the last year" heatmap, but counts
SOCIAL POSTS instead of commits, using a BLUE intensity gradient.

Input  : a JSONL (one JSON object per line) or JSON file of social-post events.
Output : an SVG embedded into the GitHub profile README.

Each post contributes points based on its type; the per-day total maps to one of four
blue intensity levels (mimicking GitHub's green 0-4 scale).

Usage:
    python generate.py                      # read data/social-posts.jsonl -> social-contributions.svg
    python generate.py --demo               # synthesize a year of sample data
    python generate.py --data path --out path --asof 2026-06-20
"""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import defaultdict
from datetime import date, timedelta
from html import escape

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

# GitHub-exact geometry.
CELL = 11            # square side (px)
GAP = 3              # gap between squares (px)
STRIDE = CELL + GAP  # 14
RADIUS = 2           # rounded corners
LEFT_GUTTER = 30     # space for Mon/Wed/Fri labels
HEADER_H = 26        # "N contributions in the last year" heading (top-left, GitHub-style)
MONTH_H = 18         # space for month labels
RIGHT_PAD = 12
LEGEND_H = 26

WEEKS = 53           # columns shown (one year)

# Blue gradient (mimics GitHub's green 0..4 ramp). Index 0 == no activity.
LEVEL_COLORS_LIGHT = ["#ebedf0", "#b6e3ff", "#6cb6ff", "#2188ff", "#0a3069"]
LEVEL_COLORS_DARK = ["#161b22", "#0a3069", "#1f6feb", "#2f81f7", "#79c0ff"]

# Text / chrome colors.
TEXT_LIGHT = "#57606a"
TEXT_DARK = "#7d8590"
# Heading color (matches GitHub's "N contributions in the last year" foreground).
HEAD_LIGHT = "#1f2328"
HEAD_DARK = "#e6edf3"
# Link color (matches GitHub's link blue) for the "How it works" affordance.
LINK_LIGHT = "#0969da"
LINK_DARK = "#58a6ff"

# Per-post point weights. Higher = more effort / more "valuable".
#   3 pts : original long-form / professional content (LinkedIn post, article, blog)
#   2 pts : original short-form (tweet / X post / quote)
#   1 pt  : amplification (retweet / repost / share)
DEFAULT_WEIGHT = 1


def weight_for(platform: str, post_type: str) -> int:
    """Map a (platform, type) pair to a point value, tolerant of loose vocabulary."""
    p = (platform or "").strip().lower()
    t = (post_type or "").strip().lower()

    # Amplification first (lowest value) so "repost"/"retweet" always wins keyword match.
    if any(k in t for k in ("retweet", "repost", "reshare", "share")):
        return 1
    # Long-form / professional original content.
    if p in ("linkedin", "blog", "medium", "substack", "newsletter"):
        return 3
    # Original short-form on X/Twitter.
    if p in ("x", "twitter"):
        return 2
    # Keyword fallback when platform is unknown.
    if any(k in t for k in ("article", "blog", "newsletter", "essay")):
        return 3
    if "tweet" in t:
        return 2
    return DEFAULT_WEIGHT


def score_to_level(score: int) -> int:
    """Map a per-day point total to a 0..4 intensity level (configurable thresholds)."""
    if score <= 0:
        return 0
    if score <= 2:
        return 1
    if score <= 5:
        return 2
    if score <= 9:
        return 3
    return 4


# --------------------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------------------

def load_posts(path: str) -> list[dict]:
    """Load posts from JSONL (preferred) or a JSON array / {"posts": [...]} document."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read().strip()
    if not raw:
        return []

    # Try a single JSON document first.
    try:
        doc = json.loads(raw)
        if isinstance(doc, dict) and "posts" in doc:
            return list(doc["posts"])
        if isinstance(doc, list):
            return doc
    except json.JSONDecodeError:
        pass

    # Fall back to JSONL (one object per line) — natural for an appended log.
    posts = []
    for line in raw.splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[", "]"):
            continue
        try:
            posts.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return posts


def make_demo_posts(asof: date, seed: int = 7) -> list[dict]:
    """Synthesize ~a year of plausible posting activity that exercises all levels."""
    rng = random.Random(seed)
    start = asof - timedelta(days=364)
    kinds = [
        ("linkedin", "post"),
        ("linkedin", "article"),
        ("blog", "post"),
        ("x", "tweet"),
        ("x", "tweet"),
        ("x", "quote"),
        ("x", "retweet"),
        ("x", "retweet"),
        ("linkedin", "repost"),
    ]
    posts = []
    d = start
    while d <= asof:
        # More likely to post on weekdays; occasional heavy "campaign" days.
        base = 0.55 if d.weekday() < 5 else 0.2
        if rng.random() < base:
            n = rng.choice([1, 1, 1, 2, 2, 3, 4])
            for _ in range(n):
                platform, ptype = rng.choice(kinds)
                posts.append({
                    "date": d.isoformat(),
                    "platform": platform,
                    "type": ptype,
                    "url": f"https://example.com/{platform}/{d.isoformat()}/{rng.randint(1000, 9999)}",
                })
        d += timedelta(days=1)
    return posts


# --------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------

def aggregate(posts):
    """Return per-day score, per-day type counts, and total post count (deduped)."""
    seen = set()
    day_score = defaultdict(int)
    day_counts = defaultdict(lambda: defaultdict(int))
    total = 0
    for post in posts:
        raw_date = str(post.get("date", "")).strip()[:10]
        if not raw_date:
            continue
        try:
            d = date.fromisoformat(raw_date)
        except ValueError:
            continue
        platform = post.get("platform", "")
        ptype = post.get("type", "")
        # Dedup on a stable key (url preferred).
        key = post.get("url") or f"{raw_date}|{platform}|{ptype}|{post.get('title', '')}"
        if key in seen:
            continue
        seen.add(key)

        w = weight_for(platform, ptype)
        day_score[d] += w
        bucket = "longform" if w >= 3 else "tweet" if w == 2 else "amplify"
        day_counts[d][bucket] += 1
        total += 1
    return day_score, day_counts, total


# --------------------------------------------------------------------------------------
# SVG rendering
# --------------------------------------------------------------------------------------

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DOW_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}  # row index (Sun=0 .. Sat=6)


def sunday_on_or_before(d: date) -> date:
    # Python weekday(): Mon=0 .. Sun=6. GitHub weeks start on Sunday.
    return d - timedelta(days=(d.weekday() + 1) % 7)


def build_svg(day_score, day_counts, total, asof: date) -> str:
    last_col_start = sunday_on_or_before(asof)
    first_col_start = last_col_start - timedelta(weeks=WEEKS - 1)

    grid_top = HEADER_H + MONTH_H  # top of the day squares
    width = LEFT_GUTTER + WEEKS * STRIDE + RIGHT_PAD
    height = grid_top + 7 * STRIDE + LEGEND_H

    out = []
    # No fixed width/height -> the viewBox lets the image scale to its container,
    # so it renders crisply on desktop browsers and shrinks to fit mobile clients.
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Social contributions over the last year">'
    )

    # Theme-adaptive styling. Every element also carries an inline `fill` (light palette)
    # so clients that ignore embedded <style> still render the full light-mode chart;
    # the CSS only *overrides* colors for dark mode (CSS beats presentation attributes).
    css = f"""
    <style>
      .scc-text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica,
        Arial, sans-serif; font-size: 10px; }}
      .scc-head {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica,
        Arial, sans-serif; font-size: 14px; font-weight: 400; }}
      .scc-link {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica,
        Arial, sans-serif; font-size: 14px; }}
      .scc-cell {{ stroke: rgba(27,31,35,0.06); stroke-width: 1px; }}
      @media (prefers-color-scheme: dark) {{
        .scc-bg {{ fill: #0d1117; }}
        .scc-text {{ fill: {TEXT_DARK}; }}
        .scc-head {{ fill: {HEAD_DARK}; }}
        .scc-link {{ fill: {LINK_DARK}; }}
        .scc-empty {{ fill: {LEVEL_COLORS_DARK[0]}; }}
        .scc-l1 {{ fill: {LEVEL_COLORS_DARK[1]}; }}
        .scc-l2 {{ fill: {LEVEL_COLORS_DARK[2]}; }}
        .scc-l3 {{ fill: {LEVEL_COLORS_DARK[3]}; }}
        .scc-l4 {{ fill: {LEVEL_COLORS_DARK[4]}; }}
        .scc-cell {{ stroke: rgba(255,255,255,0.05); stroke-width: 1px; }}
      }}
    </style>
    """
    out.append(css)
    out.append(
        f'<rect class="scc-bg" x="0" y="0" width="{width}" height="{height}" '
        f'rx="6" fill="#ffffff"/>'
    )

    # Heading, top-left — mirrors GitHub's "N contributions in the last year".
    out.append(
        f'<text class="scc-head" fill="{HEAD_LIGHT}" x="4" y="{HEADER_H - 9}">'
        f'{total} social media contributions in the last year</text>'
    )
    # "How it works" affordance, top-right on the same line. The whole chart is wrapped
    # in a link to ./social-contributions/, so clicking this text navigates there.
    out.append(
        f'<text class="scc-link" fill="{LINK_LIGHT}" x="{width - RIGHT_PAD}" '
        f'y="{HEADER_H - 9}" text-anchor="end">How it works</text>'
    )

    # Day-of-week labels (Mon / Wed / Fri).
    for row, label in DOW_LABELS.items():
        y = grid_top + row * STRIDE + CELL - 1
        out.append(
            f'<text class="scc-text" fill="{TEXT_LIGHT}" x="{LEFT_GUTTER - 6}" y="{y}" '
            f'text-anchor="end">{label}</text>'
        )

    # Month labels: above the column that contains the 1st of a month.
    placed_month = None
    for w in range(WEEKS):
        col_start = first_col_start + timedelta(weeks=w)
        for d_off in range(7):
            d = col_start + timedelta(days=d_off)
            if d.day == 1 and first_col_start <= d <= asof:
                if placed_month != (d.year, d.month):
                    x = LEFT_GUTTER + w * STRIDE
                    out.append(
                        f'<text class="scc-text" fill="{TEXT_LIGHT}" x="{x}" '
                        f'y="{grid_top - 6}">{MONTHS[d.month - 1]}</text>'
                    )
                    placed_month = (d.year, d.month)
                break

    # Cells.
    for w in range(WEEKS):
        col_start = first_col_start + timedelta(weeks=w)
        for row in range(7):
            d = col_start + timedelta(days=row)
            if d > asof:
                continue
            x = LEFT_GUTTER + w * STRIDE
            y = grid_top + row * STRIDE
            score = day_score.get(d, 0)
            level = score_to_level(score)
            cls = "scc-cell scc-empty" if level == 0 else f"scc-cell scc-l{level}"
            fill = LEVEL_COLORS_LIGHT[level]
            counts = day_counts.get(d, {})
            n_posts = sum(counts.values())
            if n_posts:
                parts = []
                if counts.get("longform"):
                    parts.append(f"{counts['longform']} post/article")
                if counts.get("tweet"):
                    parts.append(f"{counts['tweet']} tweet")
                if counts.get("amplify"):
                    parts.append(f"{counts['amplify']} repost")
                tip = f"{', '.join(parts)} on {d.isoformat()} (score {score})"
            else:
                tip = f"No posts on {d.isoformat()}"
            out.append(
                f'<rect class="{cls}" fill="{fill}" x="{x}" y="{y}" width="{CELL}" '
                f'height="{CELL}" rx="{RADIUS}" ry="{RADIUS}">'
                f'<title>{escape(tip)}</title></rect>'
            )

    # Legend: "Less [squares] More" bottom-right.
    legend_y = grid_top + 7 * STRIDE + 6
    n_swatches = len(LEVEL_COLORS_LIGHT)
    lx = width - RIGHT_PAD - (n_swatches * STRIDE) - 34
    out.append(
        f'<text class="scc-text" fill="{TEXT_LIGHT}" x="{lx - 4}" '
        f'y="{legend_y + CELL - 1}" text-anchor="end">Less</text>'
    )
    for i, color in enumerate(LEVEL_COLORS_LIGHT):
        x = lx + i * STRIDE
        cls = "scc-empty" if i == 0 else f"scc-l{i}"
        out.append(
            f'<rect class="{cls}" x="{x}" y="{legend_y}" width="{CELL}" '
            f'height="{CELL}" rx="{RADIUS}" fill="{color}"/>'
        )
    mx = lx + n_swatches * STRIDE + 4
    out.append(
        f'<text class="scc-text" fill="{TEXT_LIGHT}" x="{mx}" '
        f'y="{legend_y + CELL - 1}">More</text>'
    )

    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Generate the social contributions SVG.")
    parser.add_argument("--data", default=os.path.join(here, "data", "social-posts.jsonl"))
    parser.add_argument("--out", default=os.path.join(here, "social-contributions.svg"))
    parser.add_argument("--asof", default=None, help="YYYY-MM-DD (defaults to today)")
    parser.add_argument("--demo", action="store_true", help="synthesize sample data")
    args = parser.parse_args()

    asof = date.fromisoformat(args.asof) if args.asof else date.today()

    if args.demo or not os.path.exists(args.data):
        posts = make_demo_posts(asof)
        source = "demo data"
    else:
        posts = load_posts(args.data)
        source = args.data

    day_score, day_counts, total = aggregate(posts)
    svg = build_svg(day_score, day_counts, total, asof)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg)

    print(f"Wrote {args.out} from {source}: {total} posts, asof {asof.isoformat()}")


if __name__ == "__main__":
    main()
