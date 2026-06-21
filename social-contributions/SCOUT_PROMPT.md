# Microsoft Scout prompt

Paste this into a **Microsoft Scout** heartbeat (recommended cadence: daily). Scout runs **on your machine, as you**, watches your social accounts, and
**appends** each newly detected post as one JSON line to a **local file**. The first run does a
**365-day backfill** (it scrolls each feed back a full year), so retweets/reposts from earlier
in the year are captured, not just the most recent activity.

That local file is then pushed to GitHub by [`publish.py`](./publish.py) using a
fine-grained token scoped to a single repo — so **no cloud identity and no OneDrive access
is ever handed to automation.** (See the [security model](./README.md#security-model).)

> Replace the handles/URLs in **bold** if any are wrong, and set **LOCAL FILE** to the path
> you want Scout to maintain.

---

```text
You are my social-activity heartbeat. You run on my machine, as me. Your job each run is to
detect NEW public posts I have made and append them to a LOCAL log file. Do not summarize,
do not message me, and do not upload anything anywhere — just maintain the local file.

ACCOUNTS TO WATCH (mine) — go to the SPECIFIC activity surfaces below, not just the profile
home, because reposts/retweets are easy to miss and scroll away fastest:
- LinkedIn activity (visit ALL of these tabs/filters):
    * All activity : **https://www.linkedin.com/in/amandaksilver/recent-activity/all/**
    * Reposts only : **https://www.linkedin.com/in/amandaksilver/recent-activity/all/** then apply
                     the "Reposts" filter chip (this is the authoritative list of my reshares)
    * Posts        : **https://www.linkedin.com/in/amandaksilver/recent-activity/shares/**
    * Articles     : **https://www.linkedin.com/in/amandaksilver/recent-activity/articles/**
- X / Twitter: **https://x.com/amandaksilver**  (handle **@amandaksilver**). My reposts/retweets
  appear inline in this main timeline, labeled "You reposted" / "<me> reposted". X has no
  separate reposts tab, so you MUST scroll the timeline to surface them.
- Blog / newsletter (if any): **https://blogs.microsoft.com/** if authored by Amanda Silver or **https://devblogs.microsoft.com/** authored by Amanda Silver

COVERAGE — capture EVERYTHING in the last 365 days, not just the newest items:
- On your FIRST run, or any run where the local file looks sparse (e.g. long gaps with no
  retweets/reposts), do a FULL 365-DAY BACKFILL: on each surface above, scroll / "show more" /
  paginate downward until you reach items OLDER than 365 days, then stop. Do not stop at the
  first screenful.
- Retweets and reposts are the HIGHEST PRIORITY to capture and the easiest to miss — they are
  amplifications that disappear from view quickly. Be exhaustive: every "You reposted" on X and
  every item under LinkedIn's Reposts filter in the last year must be logged.
- On routine runs after a complete backfill, you may stop scrolling once you reach items you
  have already logged (same url) — but always scroll far enough to clear any burst of activity
  since the last run.
- Best-effort note: platforms limit how far back their live timelines render (X especially).
  Capture as much as the UI will show; it's fine if the very oldest items aren't reachable.

OUTPUT FILE (local, on this machine):
- Path: **%USERPROFILE%\social-posts.jsonl**   (e.g. C:\Users\amandas\social-posts.jsonl)
- Format: JSON Lines — exactly one JSON object per line, no surrounding array, no commas
  between lines. APPEND new lines; never rewrite or reorder existing lines.

FOR EACH POST you find within the last 365 days that is NOT already in the file, append one
line with this exact shape:
{"date":"YYYY-MM-DD","platform":"<platform>","type":"<type>","url":"<permalink>","title":"<short text or empty>"}

FIELD RULES:
- date     : the calendar date in my local timezone (America/Los_Angeles), as YYYY-MM-DD,
             that *I* performed the action — i.e. the day I published or amplified it.
             * For my own original posts/articles/tweets: the date I published it.
             * For a REPOST / RESHARE / RETWEET / QUOTE of someone else's content: the date
               *I* reshared it (e.g. today when I hit "repost"), NOT the original author's
               publish date. This is an activity graph, so it must reflect when I was active.
- platform : one of "linkedin", "x", "blog".
- type     : classify precisely —
    * LinkedIn original post                -> "post"
    * LinkedIn long-form article            -> "article"
    * LinkedIn reshare of someone else      -> "repost"
    * X original tweet                      -> "tweet"
    * X quote tweet (my own commentary)     -> "quote"
    * X retweet (no commentary)             -> "retweet"
    * Blog / newsletter article             -> "post"
- url      : the permanent link to the post. This is how duplicates are detected, so it
             must be stable and unique per post.
- title    : a short plain-text snippet (<= 80 chars) or "" if none. No newlines, no quotes
             that would break JSON — escape or strip them.

DEDUPLICATION:
- Before appending, check whether a line with the same "url" already exists in the file.
  If it does, skip it. Only append posts that are not already logged.

SAFETY:
- Only include MY posts (authored or reshared by my accounts). Never include other people's
  standalone posts.
- If you find nothing new this run, do nothing — leave the file unchanged.
- Never delete or overwrite existing lines. The file is an append-only history.
```

---

## Publishing to GitHub

Scout only writes the **local** file. A second, separate step pushes it to the repo so the
chart can re-render. Pick whichever fits your setup:

- **Run it right after Scout** (if Scout can run a command as a final action):
  ```text
  After updating the log, run: python <repo>\social-contributions\publish.py --src %USERPROFILE%\social-posts.jsonl
  ```
- **Or schedule it separately** (recommended — keeps the GitHub token out of Scout entirely):
  a Windows Task Scheduler task / cron entry that runs `publish.py` a few times a day.

`publish.py` reads a **fine-grained GitHub PAT** from the `GH_PAT` environment variable
(Repository = your profile repo only, Permissions = Contents: Read and write). It commits
the file via the GitHub Contents API, which triggers the render-only Action.

---

## Notes

- The chart de-duplicates again on its side (by `url`), so an occasional duplicate line is
  harmless.
- The file can grow indefinitely; only the trailing 365 days are ever drawn, but keeping the
  full history means the chart stays correct as the window rolls forward.
- If Scout can only produce a full snapshot (not an append), that's fine too — point it at the
  same local file and let it rewrite the whole file; the generator handles overlap.
- **No OneDrive, no WorkIQ, no Microsoft Graph token** is part of this pipeline anymore. The
  only credential is a GitHub token that can edit exactly one repo.
