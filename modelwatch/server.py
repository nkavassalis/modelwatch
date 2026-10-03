"""Serve mode: host the RSS feed over HTTP with a TTL-checked cache."""

from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .core import Refresher

log = logging.getLogger("modelwatch.server")

RSS_TYPE = "application/rss+xml; charset=utf-8"


def make_handler(refresher: Refresher):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path not in ("/", "/feed.xml", "/index.xml", "/rss"):
                if self.path == "/healthz":
                    self._send(200, b"ok\n", "text/plain")
                    return
                self._send(404, b"not found\n", "text/plain")
                return
            try:
                refresher.refresh_if_stale()
            except Exception:  # serve stale on upstream failure
                log.exception("refresh failed; serving stale feed")
            self._send(200, refresher.feed_xml.encode("utf-8"), RSS_TYPE)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def serve(cfg: Config, host: str = "0.0.0.0", port: int = 8000) -> None:
    refresher = Refresher(cfg)
    refresher.refresh_if_stale()  # prime immediately
    httpd = ThreadingHTTPServer((host, port), make_handler(refresher))
    log.info("serving RSS on http://%s:%d/feed.xml", host, port)
    httpd.serve_forever()
