"""Publish mode: write a static RSS file and upload it to S3 (+ CloudFront invalidation)."""

from __future__ import annotations

import logging

from .config import Config
from .core import Refresher

log = logging.getLogger("modelwatch.publish")


def publish(cfg: Config, force: bool = False) -> bool:
    """Refresh (respecting the cache TTL unless force) and upload the feed.

    Returns True when the feed was uploaded.
    """
    refresher = Refresher(cfg)
    fetched = refresher.refresh_if_stale(force=force)
    refresher.save_feed_file()
    if not fetched and not force:
        log.info("cache fresh; skipping S3 upload (TTL %sh not expired)",
                 cfg.cache_ttl_hours)
        return False

    if not cfg.s3.bucket:
        raise SystemExit("s3.bucket is not configured; cannot publish")

    import boto3  # optional dependency, only needed in publish mode

    s3 = boto3.client("s3", region_name=cfg.s3.region)
    s3.put_object(
        Bucket=cfg.s3.bucket,
        Key=cfg.s3.key,
        Body=refresher.feed_xml.encode("utf-8"),
        ContentType="application/rss+xml",
        CacheControl=f"max-age={int(cfg.cache_ttl_hours * 3600)}",
        ServerSideEncryption="AES256",
    )
    log.info("uploaded s3://%s/%s", cfg.s3.bucket, cfg.s3.key)

    dist = cfg.s3.distribution_id
    if dist:
        cf = boto3.client("cloudfront", region_name="us-east-1")
        try:
            etag = s3.head_object(Bucket=cfg.s3.bucket, Key=cfg.s3.key)["ETag"]
            cf.create_invalidation(
                DistributionId=dist,
                InvalidationBatch={
                    "Paths": {"Quantity": 1, "Items": [f"/{cfg.s3.key}"]},
                    "CallerReference": f"modelwatch-{etag.strip(chr(34))}",
                },
            )
            log.info("cloudfront invalidation created for %s", dist)
        except Exception:
            log.exception("cloudfront invalidation failed (upload still done)")
    return True
