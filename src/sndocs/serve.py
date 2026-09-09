"""Serve the last built site with nothing more than a static file server.

`sndocs serve` is deliberately inert: it maps `.sndocs/site/` onto localhost with
`http.server` and does no more. It never rebuilds, never watches for changes, and
never runs MkDocs or Pagefind — what it serves is exactly the tree the last
`sndocs build` wrote, search index and all. Point it at a stale or hand-edited
`.sndocs/site/` and it will serve that, byte for byte.
"""

from __future__ import annotations

import functools
import socketserver
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class _StaticServer(ThreadingHTTPServer):
    """A `ThreadingHTTPServer` that skips `http.server`'s reverse-DNS lookup on bind.

    `HTTPServer.server_bind()` calls `socket.getfqdn(host)` purely to populate
    `server_name`, which a static file server never uses — and behind a slow
    resolver that call can stall for tens of seconds before `serve` comes up.
    """

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def make_server(site_dir: Path, port: int) -> ThreadingHTTPServer:
    """Build (but don't start) a threaded static file server bound to localhost and
    rooted at `site_dir`. The root is resolved to an absolute path up front so a
    later change of working directory can't move it."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site_dir.resolve()))
    return _StaticServer((HOST, port), handler)


def serve_site(
    site_dir: Path,
    port: int = DEFAULT_PORT,
    *,
    on_ready: Callable[[ThreadingHTTPServer], None] | None = None,
) -> None:
    """Serve `site_dir` on localhost:`port` until interrupted (Ctrl+C).

    `on_ready`, if given, fires once with the live server after the socket is bound;
    `serve_site` blocks, so this is how the CLI prints the URL only once binding has
    actually succeeded.
    """
    if not site_dir.is_dir():
        raise FileNotFoundError(f"{site_dir} does not exist.")
    server = make_server(site_dir, port)
    with server:
        if on_ready is not None:
            on_ready(server)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
