"""Command line interface.

    python -m modelwatch serve   --config config.yml [--host 0.0.0.0] [--port 8000]
    python -m modelwatch publish --config config.yml [--force]
"""

from __future__ import annotations

import argparse
import logging

from .config import load_config


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", default="config.yml", help="path to config file")
    common.add_argument("-v", "--verbose", action="store_true")

    ap = argparse.ArgumentParser(prog="modelwatch", parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", parents=[common], help="host the RSS feed over HTTP")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    p_pub = sub.add_parser("publish", parents=[common], help="write static RSS and upload to S3")
    p_pub.add_argument("--force", action="store_true",
                       help="ignore cache TTL and fetch/upload anyway")

    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = load_config(args.config)
    if args.command == "serve":
        from .server import serve
        serve(cfg, host=args.host, port=args.port)
        return 0
    if args.command == "publish":
        from .publisher import publish
        uploaded = publish(cfg, force=args.force)
        print("uploaded" if uploaded else "skipped (cache fresh)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
