#!/usr/bin/env python3
"""
publish.py -- push the local social-posts log to GitHub (the "push model").

This is the client-side step. It runs on YOUR machine (right after you import your
posts into the local log) and commits the data file straight to your profile repo
using a *fine-grained* GitHub token scoped to ONLY that one repository.

Why this is the secure design
------------------------------
- No Microsoft Graph token and no OneDrive access is ever handed to automation.
- No second cloud identity acts "as you" on a schedule.
- The ONLY credential involved is a GitHub fine-grained PAT that can edit exactly
  one repo (Contents: write) and nothing else. Worst case if it leaks: someone can
  edit one GitHub repo -- not read your files.

Token setup (do this once)
--------------------------
GitHub -> Settings -> Developer settings -> Personal access tokens ->
Fine-grained tokens -> Generate new token:
  * Resource owner   : your account
  * Repository access: Only select repositories -> <owner>/<repo>
  * Permissions      : Repository permissions -> Contents -> Read and write
                       (leave everything else "No access")
  * Expiration       : as short as practical; rotate on schedule.
Store it as an environment variable named GH_PAT (never commit it).

Usage
-----
    # Windows PowerShell
    $env:GH_PAT = "github_pat_xxx"; python social-contributions/publish.py --src "$env:USERPROFILE\social-posts.jsonl"

    # macOS / Linux
    GH_PAT=github_pat_xxx python social-contributions/publish.py --src ~/social-posts.jsonl

    # Defaults: --repo AmandaSilver/AmandaSilver  --branch main
    #           --dest social-contributions/data/social-posts.jsonl

The push triggers the render-only GitHub Action, which regenerates the SVG.
Standard-library only (urllib) -- no pip installs.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"
DEFAULT_REPO = "AmandaSilver/AmandaSilver"
DEFAULT_BRANCH = "main"
DEFAULT_DEST = "social-contributions/data/social-posts.jsonl"


def _request(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "social-contributions-publish")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        payload = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(payload)
        except json.JSONDecodeError:
            return err.code, {"message": payload}


def get_remote(repo: str, dest: str, branch: str, token: str) -> tuple[str | None, str | None]:
    """Return (sha, decoded_content) for the file on the branch, or (None, None) if absent."""
    url = f"{API_ROOT}/repos/{repo}/contents/{dest}?ref={branch}"
    status, doc = _request("GET", url, token)
    if status == 404:
        return None, None
    if status != 200:
        raise SystemExit(f"GitHub GET failed ({status}): {doc.get('message', doc)}")
    content = ""
    if doc.get("content"):
        content = base64.b64decode(doc["content"]).decode("utf-8", "replace")
    return doc.get("sha"), content


def put_remote(repo, dest, branch, token, content: str, sha: str | None, message: str) -> dict:
    url = f"{API_ROOT}/repos/{repo}/contents/{dest}"
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    status, doc = _request("PUT", url, token, body)
    if status not in (200, 201):
        raise SystemExit(f"GitHub PUT failed ({status}): {doc.get('message', doc)}")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Push the local social-posts log to GitHub.")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(here, "data", "social-posts.jsonl"),
                    help="Local JSONL log to push (default: the repo's data file).")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo to publish to.")
    ap.add_argument("--branch", default=DEFAULT_BRANCH, help="Target branch.")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="Path within the repo.")
    ap.add_argument("--message", default="chore: sync social posts", help="Commit message.")
    args = ap.parse_args()

    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: set GH_PAT (a fine-grained PAT with Contents:write on the repo).",
              file=sys.stderr)
        return 2

    if not os.path.isfile(args.src):
        print(f"ERROR: source file not found: {args.src}", file=sys.stderr)
        return 2
    with open(args.src, "r", encoding="utf-8") as fh:
        local = fh.read()

    sha, remote = get_remote(args.repo, args.dest, args.branch, token)
    if remote is not None and remote == local:
        print("No changes -- remote already matches local. Nothing to push.")
        return 0

    res = put_remote(args.repo, args.dest, args.branch, token, local, sha, args.message)
    commit = (res.get("commit") or {}).get("sha", "")[:7]
    print(f"Pushed {args.dest} to {args.repo}@{args.branch} (commit {commit}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
