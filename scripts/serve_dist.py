#!/usr/bin/env python3
"""Range-capable static server for ship.sh preview (stdlib only).

python3 -m http.server ignores Range, so Chromium media elements hold the
audio connection open forever and networkidle-based browser checks time out.
Production (Cloudflare Pages) serves 206 + Accept-Ranges; this matches it.

Usage: serve_dist.py PORT DIRECTORY
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        if self.command != "GET":
            return super().send_head()
        path = self.translate_path(self.path.split("?", 1)[0])
        rng = self.headers.get("Range")
        if not rng or not rng.startswith("bytes="):
            return super().send_head()
        try:
            with open(path, "rb") as f:
                size = f.seek(0, 2)
                spec = rng[6:].split(",")[0].strip()
                if spec.startswith("-"):
                    length = int(spec[1:] or 0) or size
                    start, end = max(0, size - length), size - 1
                else:
                    start_s, _, end_s = spec.partition("-")
                    start = int(start_s or 0)
                    end = int(end_s) if end_s else size - 1
                if start >= size:
                    self.send_error(416, "Range Not Satisfiable")
                    return None
                end = min(end, size - 1)
                length = end - start + 1
                f.seek(start)
                data = f.read(length)
        except (OSError, ValueError):
            return super().send_head()
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(data)
        return None


if __name__ == "__main__":
    port = int(sys.argv[1])
    directory = sys.argv[2] if len(sys.argv) > 2 else "."
    handler = partial(RangeHandler, directory=directory)
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        httpd.serve_forever()
