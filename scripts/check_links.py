#!/usr/bin/env python3
"""Check every generated local link and fragment after building."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import concurrent.futures
import hashlib
import json
import sys
from urllib.request import HTTPError, Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / 'dist'
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.duplicates = set()
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                self.duplicates.add(attrs['id'])
            self.ids.add(attrs['id'])
        if tag in ('a', 'link', 'script', 'img'):
            href = attrs.get('href') or attrs.get('src')
            if href:
                self.links.append(href)

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--live":
        live_origin(sys.argv[2].rstrip("/"))
        return
    pages = {}
    for path in ROOT.rglob('*.html'):
        page = Page()
        page.feed(path.read_text())
        pages[path.resolve()] = page
    errors = Counter()
    checked = 0
    for path, page in pages.items():
        for duplicate in page.duplicates:
            errors[f'Duplicate id {path.relative_to(ROOT)}#{duplicate}'] += 1
        for href in page.links:
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            checked += 1
            target = (ROOT / url.path.lstrip('/') if url.path.startswith('/') else path.parent / url.path).resolve() if url.path else path
            if target.is_dir():
                target /= 'index.html'
            if not target.exists():
                errors[f'Missing destination {url.path}'] += 1
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors[f'Missing fragment {url.path}#{url.fragment}'] += 1
    print(f'{len(pages)} pages; {checked} local links; {len(errors)} failures')
    for error, count in errors.most_common(20):
        print(f'{count} × {error}')
    if not pages or errors:
        raise SystemExit(1)

def live_origin(origin):
    """Bounded production check: current bytes and every withheld work URL."""
    root = Path(__file__).resolve().parents[1]
    receipt = {"origin": origin, "checks": [], "held": 0}
    held = json.loads((root / "outputs/catalogue-quality.json").read_text())["held_works"]
    paths = ["/", "/works/", "/data/search-index.json"]
    expected = {p: hashlib.sha256((root / "dist" / p.lstrip("/") / ("index.html" if p.endswith("/") else "")).read_bytes()).hexdigest()
                for p in paths if p != "/data/search-index.json"}
    expected["/data/search-index.json"] = hashlib.sha256((root / "dist/data/search-index.json").read_bytes()).hexdigest()
    css = next((p for p in (root / "dist/assets").glob("site.css")), None)
    js = next((p for p in (root / "dist/assets").glob("site.js")), None)
    for asset in (css, js):
        if asset:
            paths.append("/assets/" + asset.name)
            expected[paths[-1]] = hashlib.sha256(asset.read_bytes()).hexdigest()
    paths.extend("/works/" + w["slug"] + "/" for w in held)
    receipt["held"] = len(held)
    def fetch(path):
        req = Request(origin + path, headers={"User-Agent": "fathers-live-gate/1"})
        try:
            with urlopen(req, timeout=12) as response:
                body = response.read()
                status = response.status
                headers = dict(response.headers.items())
        except HTTPError as exc:
            body = exc.read()
            status = exc.code
            headers = dict(exc.headers.items())
        except Exception as exc:
            return {"path": path, "error": str(exc)}
        row = {"path": path, "status": status, "sha256": hashlib.sha256(body).hexdigest(),
               "cache": headers.get("cf-cache-status"), "age": headers.get("age")}
        if path.startswith("/works/") and path.endswith("/") and path not in ("/works/",):
            row["ok"] = status == 404 and b"Page unavailable" in body and not any(x in body.decode("utf-8", "ignore") for x in ("Lemma-led open", "Rem early", "Rem mid", "Rem CLOSEOUT"))
        else:
            row["ok"] = status == 200 and row["sha256"] == expected[path]
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(fetch, paths))
    receipt["checks"] = rows
    (root / "outputs/catalogue-live.json").write_text(json.dumps(receipt, indent=2) + "\n")
    failed = [r for r in rows if not r.get("ok")]
    print(json.dumps({"origin": origin, "checked": len(rows), "held": len(held), "failed": len(failed)}))
    if failed:
        for row in failed[:20]:
            print(json.dumps(row), file=sys.stderr)
        raise SystemExit(1)
if __name__ == '__main__':
    main()
