# AGENTS.md — guidance for AI coding agents working on modelwatch

## What this project is

A small Python CLI that turns the Hugging Face *trending* leaderboard into an
RSS 2.0 feed. A model enters the feed the **first time** it appears in the top
`top_n` positions; it is never repeated, even if it leaves and re-enters.
Two run modes: `serve` (HTTP host with TTL cache) and `publish` (static file
to S3, optional CloudFront invalidation). MIT licensed; keep it that way.

## Layout

```
modelwatch/
  config.py     YAML config -> dataclasses; website_to_api_url() URL translation
  fetcher.py    HTTP calls to HF JSON API; TrendingModel; label mapping
  state.py      State: JSON file with seen-set, feed entries, last_fetch; TTL check
  feed.py       render_feed() -> RSS 2.0 XML string (stdlib, escaped)
  core.py       Refresher: the shared "refresh_if_stale(force)" transaction
  server.py     serve mode (stdlib http.server)
  publisher.py  publish mode (boto3 import is lazy/on purpose)
  cli.py        argparse entry: serve | publish [--force]
tests/test_modelwatch.py   pytest, all network mocked
crontab.example, config.example.yml
```

## Invariants — do not break these

1. **First-seen only.** `State.record()` must never re-add a model id that is
   in the persisted `seen` set. There is no expiry on `seen`. Tests enforce this.
2. **TTL honoured everywhere.** Hugging Face must not be fetched unless
   `State.cache_expired(ttl)` or `force=True`. In publish mode, a fresh cache
   must also skip the S3 upload entirely (that's what makes hourly cron cheap).
3. **Feeds are append-only history.** `entries` (newest-first, capped by
   `MAX_ENTRIES`) is rendered from state, so restarts/redeploys never lose
   items a reader already saw.
4. **RSS entries keep their shape:** title = model id (`Owner/Model`),
   `<category>` = human pipeline label, `<link>`/guid from the model id.
5. **Determinism/testability:** no network in tests — monkeypatch
   `modelwatch.core.fetch_trending` or `modelwatch.fetcher.requests.get`.
   Timestamps are injectable (`State.record(now=...)`).

## Conventions

- Runtime deps: `requests`, `PyYAML` only. `boto3` is an optional extra and must
  stay a lazy import inside `publish()` so serve mode never needs it.
- Keep serve mode stdlib-only for the HTTP parts (no flask/fastapi).
- State is one human-readable JSON file; keep the schema additive & backwards
  compatible (`State` uses `setdefault` for forward migration).
- Config keys mirror `config.example.yml`; new keys need defaults in
  `config.py::load_config` plus a table row in README.md.
- Errors during a fetch must not destroy state: serve mode serves the stale
  feed, publish mode exits before mutating the state file.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # setup
.venv/bin/python -m pytest tests/ -q                          # tests (must pass)
.venv/bin/python -m modelwatch serve --port 8000              # run feed server
.venv/bin/python -m modelwatch publish --force                # one-shot upload
```

Reference deployment (don't point experiments at it without `--force`, and
never delete the bucket/policy): bucket `modelwatch-rss`, CloudFront
`E2MSFTBRSGB0XM`, feed at https://du62m9e5v3var.cloudfront.net/feed.xml,
hourly cron for the `nick` user running `publish` (the TTL limits actual
fetches to one per 24h).

## Gotchas

- `https://huggingface.co/models?sort=trending` is HTML; the API equivalent is
  `sort=trendingScore&direction=-1` — that translation lives in
  `config.website_to_api_url()` and is unit-tested. `limit=` is always
  rewritten from `top_n`.
- Pipeline labels come from `/api/models-tags-by-type`; if that fetch fails the
  `_humanize()` fallback approximates them ("text-to-image" ->
  "Text-to-Image", "automatic-speech-recognition" -> "Automatic Speech
  Recognition"). Prefer real labels when available.
- AWS S3 bucket names are globally unique and lowercase: the bucket here is
  `modelwatch-rss`, not `modelWatch`.
- Publishing needs the bucket policy to reference the distribution ARN; if you
  recreate the distribution, update the policy and `s3.distribution_id`.
- CloudFront uses the default `*.cloudfront.net` certificate; custom domains
  would need an ACM cert in us-east-1.

## Adding a feature — recipe

1. Write the failing test in `tests/test_modelwatch.py` with mocked network.
2. Implement in the smallest module that owns the concern (see layout).
3. Update `config.example.yml` + README table if config changed.
4. Run the full suite; commit with a conventional-commit style message
   (`feat:`, `fix:`, `docs:`).
