"""Serve the browser_compute harness files (test-only).

The harness page, the component (ui/components/browser_compute/) and the fake
Pyodide must share one origin, as the component and its workers do under
Streamlit. ``lookup`` maps a URL path to a file under the repo root and is
used two ways:

* run_playwright.py answers requests for a fake origin from it through
  Playwright request routing (no socket needed; the agent sandbox forbids
  binding one);
* ``python3 tests/browser_compute_harness/serve.py [port]`` serves it on
  127.0.0.1 for manual use, then open
  http://127.0.0.1:<port>/tests/browser_compute_harness/harness.html
"""
from __future__ import annotations

import http.server
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[2]
HARNESS_PATH = "/tests/browser_compute_harness/harness.html"
TYPES = {".html": "text/html", ".js": "text/javascript", ".py": "text/plain", ".json": "application/json"}


def lookup(url: str) -> tuple[Path, str] | None:
    """(file, content type) for a URL or path under the repo root, else None."""
    rel = unquote(urlsplit(url).path).lstrip("/")
    path = (REPO / rel).resolve()
    if REPO not in path.parents or not path.is_file():
        return None
    return path, TYPES.get(path.suffix, "application/octet-stream")


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        found = lookup(self.path)
        body = found[0].read_bytes() if found else b"not found"
        self.send_response(200 if found else 404)
        self.send_header("Content-Type", found[1] if found else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"http://127.0.0.1:{port}{HARNESS_PATH}", flush=True)
    server.serve_forever()
