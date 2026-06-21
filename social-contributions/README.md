# Social Contributions Chart

A widget for the profile README that looks exactly like GitHub's **"contributions over
the last year"** heatmap — but it counts **social posts** instead of commits, using a
**blue** intensity gradient.

![Social contributions](./social-contributions.svg)

---

## How it works

GitHub renders its real contribution graph fresh on every request, but a README can only
embed a **static image**. So this widget is a committed `social-contributions.svg` that is
**regenerated on a schedule**. The generator always renders the *trailing 365 days ending
today*, so each run rolls the window forward exactly like GitHub's graph (which itself only
advances once per day).

```
Microsoft Scout (heartbeat, runs on YOUR machine, as you)
        │  appends one line per detected post
        ▼
local file: social-posts.jsonl   ◄── the status log (stays on your machine)
        │  publish.py  pushes via a fine-grained GitHub token (1 repo, Contents:write)
        ▼
repo: social-contributions/data/social-posts.jsonl
        │  generate.py  (GitHub Action, render-only — no credentials)
        ▼
repo: social-contributions/social-contributions.svg  ──►  embedded in README.md
```

This is a **push model**: the only thing that touches your accounts (Scout) runs locally as
you, and it *pushes* the result to GitHub. **No cloud identity, no OneDrive access, and no
Microsoft Graph token is ever handed to automation** — see [Security model](#security-model).

Two refresh drivers keep it current:

| Driver | What it does | Cadence |
| --- | --- | --- |
| **`publish.py`** (client-side) | Pushes the latest local `social-posts.jsonl` into the repo using a fine-grained GitHub PAT, which triggers the Action to re-render. | After Scout runs / scheduled task |
| **GitHub Action** (`.github/workflows/social-contributions.yml`) | Re-runs `generate.py` and commits the SVG if it changed. Rolls the trailing-year window even when no new posts arrive. Holds no Microsoft credentials. | Every 6 h + on data push |

> **Want literally per-visit freshness?** Host `generate.py` behind a tiny serverless
> endpoint that returns the SVG per request and embed that URL instead. The scheduled
> approach above matches GitHub's day-granularity behavior without running a server.

---

## Data format (the status log)

**File:** `social-posts.jsonl` — a **local file** on your machine that Microsoft Scout
maintains (it never has to leave your machine except as the committed copy in this repo).
It's **JSON Lines** (one JSON object per line), which is append-friendly and suits a
heartbeat that adds entries over time.

```jsonl
{"date": "2026-06-19", "platform": "linkedin", "type": "post",    "url": "https://www.linkedin.com/posts/...", "title": "Work IQ APIs are GA"}
{"date": "2026-06-19", "platform": "x",        "type": "tweet",   "url": "https://x.com/amandaksilver/status/123"}
{"date": "2026-06-18", "platform": "x",        "type": "retweet", "url": "https://x.com/amandaksilver/status/124"}
{"date": "2026-06-17", "platform": "blog",     "type": "post",    "url": "https://example.com/post", "title": "Shipping with customers"}
```

| Field | Required | Notes |
| --- | --- | --- |
| `date` | yes | `YYYY-MM-DD` in your local timezone — the day **you** were active. For your own posts, the publish date; for a **repost/reshare/retweet**, the date **you** amplified it (not the original author's date). |
| `platform` | yes | `linkedin`, `x` (or `twitter`), `blog`, `medium`, `substack`, … |
| `type` | yes | `post`, `article`, `tweet`, `quote`, `retweet`, `repost`, `share`, … |
| `url` | recommended | Used to **de-duplicate** repeated heartbeat entries. |
| `title` | optional | Used in the tooltip; helps dedup when there's no URL. |

A plain JSON array or `{"posts": [...]}` document is also accepted.

---

## Scoring → blue gradient

Each post earns points by effort; the per-day total maps to a blue intensity level
(mimicking GitHub's 0–4 green scale).

| Points | What counts | Examples |
| --- | --- | --- |
| **3** | original long-form / professional | LinkedIn post or article, blog/Medium/Substack post |
| **2** | original short-form | original tweet / X post / quote tweet |
| **1** | amplification | retweet, repost, reshare, share |

| Daily score | Level | Light | Dark |
| --- | --- | --- | --- |
| 0 | L0 | `#ebedf0` | `#161b22` |
| 1–2 | L1 | `#b6e3ff` | `#0a3069` |
| 3–5 | L2 | `#6cb6ff` | `#1f6feb` |
| 6–9 | L3 | `#2188ff` | `#2f81f7` |
| 10+ | L4 | `#0a3069` | `#79c0ff` |

Weights and thresholds live at the top of `generate.py` (`weight_for`, `score_to_level`) —
tweak them to taste.

Every square also carries an **inline `fill`** (light palette); the embedded `<style>` only
*overrides* colors for dark mode. So clients that ignore SVG `<style>` (some mobile in-app
webviews / image proxies) still show the correct chart, and the image scales responsively
via its `viewBox` on small screens.

---

## Running it manually

```bash
python social-contributions/generate.py                 # data/social-posts.jsonl -> SVG
python social-contributions/generate.py --demo          # synthesize a year of sample data
python social-contributions/generate.py --asof 2026-06-20
```

No third-party dependencies — standard-library Python 3.9+.

---

## The Microsoft Scout prompt

Configure a Scout heartbeat with the prompt in [`SCOUT_PROMPT.md`](./SCOUT_PROMPT.md).
It tells Scout to detect new LinkedIn/blog/X activity and **append** matching lines to a
local `social-posts.jsonl`, which [`publish.py`](./publish.py) then pushes to the repo.

---

## Backfilling older X (Twitter) history

X's live timeline only scrolls back a limited distance, so Scout can't see retweets/tweets
from earlier in the year. Your official **account archive** has the complete history. To fill
the gaps:

1. On X: **Settings → Your account → Download an archive of your data**. When it's ready,
   unzip it and find `data/tweets.js`.
2. Run the importer once — it appends any missing posts to your local file (append-only,
   de-duplicated by URL):
   ```powershell
   python social-contributions/import_x_archive.py "C:\path\to\archive\data\tweets.js"
   ```
3. Then publish as usual: `python social-contributions/publish.py --src "$env:USERPROFILE\social-posts.jsonl"`.

Useful flags: `--until 2026-04-01` (only import older posts, to avoid overlapping Scout's
recent live captures), `--since`, `--include-replies`, `--no-retweets`, and `--dry-run` to
preview. It classifies `RT @…` as `retweet` and everything else as `tweet`, converts archive
timestamps to your local (Pacific) calendar date, and skips `@`-replies by default.
Standard-library only — no network, no credentials.

---

## Security model

This pipeline is deliberately built so that **automation never holds a credential that can
read your files.** The design separates the two concerns:

| Component | Where it runs | Identity it uses | What it can touch |
| --- | --- | --- | --- |
| **Microsoft Scout** | Your machine | You (interactive, local) | Reads your own social accounts; writes one local file |
| **`publish.py`** | Your machine (or a local scheduled task) | A **fine-grained GitHub PAT** | Edits **one repo**, Contents only — nothing else |
| **GitHub Action** | GitHub-hosted runner | The repo's built-in `GITHUB_TOKEN` | Commits the re-rendered SVG to this repo |

Why this is the secure shape:

- **No on-behalf-of (OBO) cloud agent.** Nothing runs unattended *as you* against Microsoft
  Graph. The component that reads your accounts (Scout) only runs when you run it, locally.
- **No OneDrive / Graph token in CI.** The GitHub Action holds zero Microsoft credentials —
  it only renders committed data, so a poisoned data file can at worst produce a wrong chart,
  never exfiltrate anything (the generator is stdlib-only: no network, no `eval`/`exec`, and
  it emits only aggregate daily counts — never the post URLs or titles).
- **Smallest possible blast radius.** The only standing secret is a GitHub fine-grained PAT
  scoped to **one repository, Contents: write**. If it leaked, the worst case is "someone can
  edit one GitHub repo" — not "someone can read my files."

### Setting up the fine-grained GitHub token

GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens →
Generate new token**:

- **Resource owner:** your account
- **Repository access:** *Only select repositories* → your profile repo
- **Permissions:** *Repository permissions → Contents → Read and write* (everything else
  left at *No access*)
- **Expiration:** as short as practical; rotate on a schedule

Store it on your machine as the `GH_PAT` environment variable. **Never commit it.**

> **Public-repo note:** the render Action only runs on `push` to `main`, `schedule`, and
> manual `workflow_dispatch` — never on `pull_request` from forks — so no fork PR can reach
> a credentialed job.

### If you want the file to live in M365 instead

If a hard requirement says the status log must stay in Microsoft 365 and GitHub must *pull*
it, don't use a personal-OneDrive app permission (those are tenant-wide — `Files.Read.All` —
which is *more* access, not less). Instead put the file in a **dedicated SharePoint site**
and grant a purpose-built app **`Sites.Selected`** read access to just that one site, and
have the Action authenticate via **GitHub→Entra OIDC federation** (no stored secret). That's
the least-privilege *pull* design — but the **push model above is simpler and strictly safer**,
so prefer it unless you truly need the pull.
