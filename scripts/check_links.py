#!/usr/bin/env python3
"""Check every generated local link and fragment after building."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
if __name__ == '__main__':
    main()
