# AI Updates Monitor on AWS (EventBridge + Lambda + DynamoDB + SNS/SES)

This document describes how to build an automatic “AI/ML updates monitor” that polls a curated set of first‑party pages (company news, changelogs, blogs, GitHub releases) and notifies you when something new appears.

> **Key design principles**
> - Prefer **structured signals** (RSS/Atom, GitHub Releases) over HTML scraping.
> - Use **dedupe + fingerprints** so you never get the same alert twice.
> - Keep it **simple + cheap**: scheduled Lambda, small DynamoDB table, SNS/SES notifications.
> - **Do not run the Lambda in a VPC** (avoids NAT costs and connectivity complexity).
> - Keep observability **lightweight** (minimal logging; no heavy CloudWatch pipelines).

---

## 1) Goal and non‑goals

### Goal
- On a fixed cadence (e.g., every 30–60 minutes), detect **new posts/entries/releases** across many AI/ML update pages and notify via email.

### Non‑goals
- Perfect semantic diffs of arbitrary webpages.
- Monitoring content behind logins or highly dynamic pages without stable extraction hooks.
- Heavy analytics/monitoring pipelines (this is a lightweight utility).

---

## 2) High‑level architecture

**EventBridge (schedule)** → **Lambda (poll & diff)** → **DynamoDB (state/dedupe)** → **SNS/SES (notify)**

### Request flow (per run)
1. EventBridge triggers Lambda on a schedule (rate/cron).
2. Lambda loads `sources.yaml` (or sources config from S3 / Parameter Store).
3. For each source:
   - Fetch using conditional headers (ETag / Last‑Modified) when available.
   - Extract meaningful “latest items” (adapter-specific).
   - Compute a fingerprint (hash).
   - Compare to last fingerprint stored in DynamoDB.
4. If changed:
   - Add entry to a digest.
   - Update DynamoDB with new fingerprint and fetch validators.
5. If digest has changes:
   - Send one email notification (digest) via SNS or SES.

---

## 3) Components and why they exist

### EventBridge schedule
- Runs at your chosen cadence (30/60 minutes).
- Triggers Lambda reliably.

### Lambda
- Fetches sources, computes fingerprints, and decides what’s new.

> **Important:** Keep Lambda **out of a VPC** unless you have a strong reason.
> - Most monitored pages are public internet.
> - VPC Lambda requires NAT for outbound internet and can add significant recurring cost and complexity.

### DynamoDB
- Stores per-source state (last fingerprint, validators).
- Ensures dedupe so each update triggers once.

### SNS or SES (Email)
- **SNS email subscription** is the simplest (topic → email).
- **SES** gives nicer control/formatting; also better for scaling email deliverability.

---

## 4) Source adapters (how “new updates” are detected)

Use a small set of adapter types. Each source URL is assigned an adapter.

### A) RSS/Atom (preferred)
- Parse top N entries.
- Fingerprint based on entry GUID/link + timestamp + title (or just GUIDs).
- Benefit: very low noise, very reliable.

### B) GitHub Releases / Tags (preferred for OSS components)
- Poll `releases.atom` (simple) or GitHub API.
- Fingerprint based on newest release tag(s) + published timestamp.
- Benefit: exact release events.

### C) HTML “article list” (no feed)
- Fetch page and extract only the list container (cards/list items).
- Build a list of `(title, link, date)` for top N items.
- Fingerprint the serialized list.
- Use selector-based extraction to reduce noise.

### D) HTML changelog pages
- Extract headings/entries (e.g., release version headings, bullet lists).
- Fingerprint normalized extracted content.

### E) JSON endpoints (optional)
- If a site is JS-rendered but uses a stable JSON API, poll that API instead of HTML.
- Fingerprint stable fields in response.

---

## 5) Configuration model (source registry)

Store sources in a single config file (YAML/JSON), or in S3/SSM Parameter Store.

Each entry should include:
- `id`: unique identifier
- `org`: organization name
- `name`: human-friendly label
- `adapter`: `rss | atom | github_releases_atom | html_articles | html_changelog | json`
- `url`: URL to poll (or `repo` for GitHub if using API)
- optional:
  - `selector`: CSS selector for HTML extraction (highly recommended)
  - `max_items`: N newest items to fingerprint (e.g., 10)
  - `ignore_patterns`: regex patterns to remove dynamic tokens
  - `headers`: optional custom headers (rarely needed)

**Why config-driven?**  
So your coding agent can add hundreds of sources without editing core code.

---

## 6) DynamoDB schema (state and dedupe)

Table name: e.g., `ai_updates_state`

Primary key:
- `source_id` (string)

Attributes:
- `fingerprint` (string) — hash of meaningful extracted signal
- `etag` (string, optional) — last ETag seen
- `last_modified` (string, optional) — last Last‑Modified
- `last_seen_utc` (string) — timestamp of last successful processing
- `last_item_key` (string, optional) — e.g., latest RSS GUID or GitHub tag

### Deduping logic
- Only notify if `new_fingerprint != stored_fingerprint`
- Then persist new fingerprint.
- This is idempotent and handles retries safely.

---

## 7) Fetching strategy (polite and cheap)

### Conditional GET
When fetching HTML or feed URLs:
- If you previously stored `etag`, send `If-None-Match: <etag>`
- If you stored `last_modified`, send `If-Modified-Since: <date>`
- If server returns `304 Not Modified`, skip parsing and treat as “no change”.

### Concurrency
- Use limited parallelism to keep runs short (e.g., 5–15 concurrent fetches).
- Respect rate limits:
  - set a stable `User-Agent`
  - use timeouts (10–20s)
  - back off on 429/503 responses

---

## 8) Notification strategy

### Digest per run (recommended)
- One email per run when there are any changes:
  - subject: “AI Updates: X sources changed”
  - body: list of changed sources with top items/links

This avoids spamming and reduces email volume.

### SNS email (simple)
- Lambda publishes to SNS topic.
- Topic has an email subscription (you confirm via the initial SNS email).

### SES email (more control)
- Verify sender identity (domain/email).
- Send direct email with a clean subject/body.
- Still keep it digest-based.

---

## 9) Deployment options (AWS-native)

### Minimal AWS setup
- EventBridge schedule (rate/cron)
- Lambda function
- DynamoDB table
- SNS topic + email subscription **OR** SES verified identity

### Source config storage
- Option 1: bundle `sources.yaml` with Lambda code (fastest)
- Option 2: store `sources.yaml` in S3 and load at runtime
- Option 3: store JSON in SSM Parameter Store (easy edits)

---

## 10) Minimal observability (no heavy CloudWatch)

CloudWatch Logs are created automatically for Lambda; you can keep this extremely lightweight:

- Log only:
  - run start/end
  - number of sources checked
  - number of changes detected
  - errors summarized per source (no huge payload dumps)
- Set a **short log retention** (e.g., 3–7 days) to reduce clutter/cost.
- Skip custom dashboards, detailed metrics, or alarms unless you need them.

> For a simple use case, **no extra CloudWatch setup is fine** beyond minimal logs.

---

## 11) Operational considerations

### Keep Lambda out of VPC
- Avoid NAT gateway costs.
- Avoid egress complexity.
- Public polling needs outbound internet.

### Handle failures gracefully
- If one source fails, continue others.
- Retry strategy:
  - allow EventBridge/Lambda retry behavior
  - keep idempotent state updates with DynamoDB fingerprints

### Reduce false positives on HTML
- Always use selector-based extraction
- Normalize whitespace
- Strip scripts/styles
- Consider ignore_patterns for timestamps (“Updated 2 hours ago”)

---

## 12) Coverage: will this handle all sources in the full URL list?
Yes—**as long as every URL is assigned an adapter**.

- RSS/Atom sources → `rss`/`atom`
- GitHub release sources → `github_releases_atom`
- HTML-only news/blog/changelog pages → `html_articles` / `html_changelog`
- JS-heavy pages → find underlying JSON API (`json` adapter) or accept noisier HTML fallback

Some pages may require one-time “adapter tuning” (selector discovery or API discovery), but the system architecture supports all of them.

---

## 13) Implementation plan for your coding agent
1. Implement core pipeline:
   - EventBridge → Lambda → DynamoDB → SNS (digest on change)
2. Implement adapters in order:
   1) RSS/Atom
   2) GitHub releases (Atom)
   3) HTML articles list
   4) HTML changelog
   5) JSON adapter (optional)
3. Add conditional GET and store ETag/Last-Modified.
4. Add lightweight logging and short retention.
5. Add S3/SSM config loading (optional).

---

## Appendix: Recommended defaults
- Schedule: every **30 minutes**
- Lambda memory: **512 MB**
- Timeout: **60–120 seconds**
- Concurrency: **10**
- Digest: **one email per run if changes exist**
- No VPC
- Minimal logs + 3–7 day retention
