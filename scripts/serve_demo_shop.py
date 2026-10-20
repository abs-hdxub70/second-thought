"""Serve the fictional demo shop for the browser extension at http://127.0.0.1:8770/demo-shop/."""

from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "extension"


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        path = path.split("?")[0]
        if path.startswith("/demo-shop"):
            path = path[len("/demo-shop"):] or "/"
            demo = (ROOT / "demo").resolve()
            target = (demo / path.lstrip("/")).resolve()
            if target == demo or demo in target.parents:
                return str(target)
        return str(ROOT / "demo" / "__missing__")

    def log_message(self, fmt, *args):  # quiet
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    port = ap.parse_args().port
    server = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler))
    print(f"Demo shop on http://127.0.0.1:{port}/demo-shop/")
    server.serve_forever()


if __name__ == "__main__":
    main()
