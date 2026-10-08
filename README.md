# modelwatch

An RSS interface to [Hugging Face trending models](https://huggingface.co/models?sort=trending).

modelwatch watches the top N positions of the Hugging Face trending leaderboard and publishes an RSS 2.0 feed containing each model **the first time it appears** in that window. Once a model has been reported it is remembered forever — if it dips out of the top N and comes back later, it will *not* reappear in the feed.

Each RSS entry carries:

- **title** — the model id, e.g. `Qwen/Qwen-Image-2.1`
- **category** — the human-readable pipeline tag, e.g. `Text-to-Image`
- **link** — `https://huggingface.co/<model-id>`
- **pubDate** — when *modelwatch first saw the model enter the top N* (i.e. when
  it was first published to this feed), not the model's release date
- **dcterms:created** — the model's actual upload date on Hugging Face (from the
  API's `createdAt`), also repeated in plain text in the description
  ("Uploaded to Hugging Face 2026-09-18")

So `<pubDate>` answers "when did it hit the leaderboard feed" and
`<dcterms:created>` answers "when did the model actually come out" — a model
uploaded long ago that only recently went viral will show an older
`dcterms:created` with a recent `pubDate`.

Hugging Face is only fetched when the configured cache TTL expires (default 24 hours), so you can run the publisher from cron every hour without hammering their API.

## Live feed

The reference deployment publishes to CloudFront:
`https://du62m9e5v3var.cloudfront.net/feed.xml`

## How it works

Instead of scraping HTML, modelwatch translates the browse URL you configure
(`https://huggingface.co/models?sort=trending`) into the JSON API endpoint the
site itself uses (`https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=<top_n>`),
so ranking matches the website exactly. A raw `/api/...` URL can also be configured
directly. Pipeline-tag labels (e.g. `text-to-image` → `Text-to-Image`) come from
`https://huggingface.co/api/models-tags-by-type`, with a built-in humanizer as fallback.

State lives in a single JSON file (`state_dir/state.json`) holding:

- `seen` — every model id ever observed in the top N (never forgotten)
- `entries` — feed items (newest first, capped at 300) so your feed reader keeps history
- `last_fetch` — timestamp used to enforce the cache TTL

## Install

```bash
git clone https://github.com/nkavassalis/modelwatch.git
cd modelwatch
python3 -m venv .venv
.venv/bin/pip install -e .          # add "[s3]" if you will use publish mode
cp config.example.yml config.yml    # edit to taste
```

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `source_url` | `https://huggingface.co/models?sort=trending` | URL to watch (browse URL or raw HF API URL; `limit` is always overridden by `top_n`) |
| `top_n` | `100` | Monitor the top N trending positions |
| `cache_ttl_hours` | `24` | Minimum hours between fetches of Hugging Face (also the S3/CloudFront freshness window) |
| `state_dir` | `./.modelwatch` | Where `state.json` and the cached `feed.xml` live |
| `feed.title/description/site_url` | see example | Channel metadata |
| `s3.bucket` | *(empty)* | Target bucket for publish mode |
| `s3.key` | `feed.xml` | Object key |
| `s3.region` | `us-east-1` | Bucket region |
| `s3.distribution_id` | *(empty)* | Optional CloudFront distribution; when set an invalidation for the feed key is issued after upload |

## Modes

### 1. Serve — host the feed

```bash
modelwatch serve --config config.yml --host 0.0.0.0 --port 8000
```

Serves the RSS at `/`, `/feed.xml` (plus `/healthz`). Every request checks the
cache TTL and only fetches Hugging Face when it has expired; if a fetch fails,
the stale feed is served.

### 2. Publish — static RSS file to S3 + CloudFront

```bash
modelwatch publish --config config.yml          # respects the cache TTL
modelwatch publish --config config.yml --force  # fetch + upload regardless
```

Writes `.modelwatch/feed.xml` locally, uploads it to
`s3://<bucket>/<key>` with `Cache-Control: max-age=<ttl>` and SSE, and (if
`distribution_id` is set) invalidates the CloudFront path. When the TTL has not
expired the run exits without touching S3 — which makes it cheap to run hourly
from cron:

```cron
# See crontab.example
0 * * * * cd /opt/modelwatch && /opt/modelwatch/.venv/bin/python -m modelwatch publish --config /opt/modelwatch/config.yml >> /opt/modelwatch/publish.log 2>&1
```

> **Keep cron alive:** on minimal hosts (containers without systemd/init) the
> cron daemon is not started at boot and the package can be autoremoved — the
> feed then goes silently stale. `deploy/ensure-cron.sh` is installed as
> `/etc/profile.d/zz-ensure-cron.sh` on the reference box to auto-restart cron
> at every login; copy it if you redeploy. If the hosted feed is old, first
> check `pgrep cron` and `crontab -l`.

### Deploying the S3 + CloudFront target

The bucket must be private; CloudFront reads it via an Origin Access Control:

```bash
aws s3api create-bucket --bucket modelwatch-rss --region us-east-1
aws s3api put-public-access-block --bucket modelwatch-rss \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false

OAC=$(aws cloudfront create-origin-access-control \
  --origin-access-control-config '{"Name":"modelwatch-oac","OriginAccessControlOriginType":"s3","SigningBehavior":"always","SigningProtocol":"sigv4"}' \
  --query OriginAccessControl.Id --output text)

DIST=$(aws cloudfront create-distribution --distribution-config '{ ... OAC, redirect-to-https, CloudFrontDefaultCertificate ... }' ...)
# ^ full JSON in git history / aws cli docs; or import an existing distribution id into config.yml

aws s3api put-bucket-policy --bucket modelwatch-rss --policy '{"Version":"2012-10-17","Statement":[{
  "Effect":"Allow","Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"s3:GetObject",
  "Resource":"arn:aws:s3:::modelwatch-rss/*",
  "Condition":{"StringEquals":{"AWS:SourceArn":"arn:aws:cloudfront::<ACCOUNT_ID>:distribution/<DIST_ID>"}}}]}'
```

With the default CloudFront certificate the feed is served over SSL at
`https://<distribution-domain>/<key>`. To use your own domain, add an alias +
ACM certificate (in us-east-1) and a CNAME to the distribution domain.

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
```

All Hugging Face calls are mocked; the suite covers config parsing, URL
translation, first-seen-only state transitions, TTL behaviour, feed XML
structure/escaping, and the publish/serve refresh logic.

## Notes & limits

- Feed history is capped at 300 entries in state; the `seen` set grows forever (a few KB per model).
- The trending API returns up to 1000 models per call; `top_n` above that would need pagination (not implemented).
- modelwatch sets a descriptive `User-Agent`; please don't lower the TTL aggressively.

## License

MIT — see [LICENSE](LICENSE).
