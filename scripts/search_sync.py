#!/usr/bin/env python3
"""Semantic search sync for viapatrum.org (owner 2026-10-03: "semantic search is a must").

  python3 scripts/search_sync.py export   # dist/data/search shards -> outputs/search-docs/*.md + meta.json
  python3 scripts/search_sync.py upload   # embed new/changed chunks into Vectorize, delete removed

Backend: Cloudflare Vectorize index "viapatrum-search" (1024-d, cosine) with
Workers AI @cf/qwen/qwen3-embedding-0.6b document embeddings. functions/api/search.js
embeds the query with the same model, takes the nearest chunks, reranks them with
@cf/baai/bge-reranker-base and returns one result per passage. (AI Search would
replace this backend later without changing /api/search.)

One markdown document per live passage (work section or topic excerpt), split
into ~1,600-character chunks with 200 characters of overlap. Vector metadata
holds the document key and the chunk text (for reranking and snippets).
outputs/search-docs/.uploaded.json records the sha and vector ids per key, so
each run sends only what changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "outputs" / "search-docs"
ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "2c267ab06352ba2522114c3081a8c5fa")
INDEX = os.environ.get("VP_SEARCH_INDEX", "viapatrum-search")
EMBED = "@cf/qwen/qwen3-embedding-0.6b"
DIMS = 1024
CF = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
CHUNK, OVERLAP = 1600, 200


def key_for(item: dict) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", f"{item['kind']}__{item['id']}")[:180] + ".md"


def writer_dates():
    """name -> (sort year or None, display dates), from the site's own author
    dates (data/author-dates.json via build_site), so /api/ask can order quotes
    by date. Meta only: nothing is re-embedded. Without PyYAML (build_site
    needs it) the fields are simply left out."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_site as B  # noqa: E402
    except Exception as e:  # pragma: no cover - only without the build venv
        print(f"writer dates skipped: {e}", file=sys.stderr)
        return lambda _name: (None, "")
    cache: dict[str, tuple] = {}

    def look(name: str):
        if name not in cache:
            y = B.author_sort_year(name) if name else 9999
            cache[name] = (None if y == 9999 else y, B.author_dates_display(name) if name else "")
        return cache[name]
    return look


def export() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_site as B  # noqa: E402
    idx = B.load_search_docs(ROOT / "dist" / "data")
    DOCS.mkdir(parents=True, exist_ok=True)
    meta, keep = {}, set()
    dates_for = writer_dates()
    for it in idx:
        text = (it.get("text") or "").strip()
        if not text:
            continue
        key = key_for(it)
        keep.add(key)
        body = f"# {it.get('title', '')}\n\nWriter: {it.get('author', '')}\n\n{text}\n"
        path = DOCS / key
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            path.write_text(body, encoding="utf-8")
        meta[key] = {"title": it.get("title", ""), "author": it.get("author", ""), "href": it.get("href", ""),
                     "kind": it.get("kind", "")}
        year, dates = dates_for(it.get("author", ""))
        if year is not None:
            meta[key]["year"] = year
        if dates:
            meta[key]["dates"] = dates
    for old in DOCS.glob("*.md"):
        if old.name not in keep:
            old.unlink()
    (DOCS / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"exported {len(meta)} documents")
    return 0


def chunks(body: str) -> list[str]:
    head, _, text = body.partition("\n\n")
    writer, _, text = text.partition("\n\n")
    prefix = f"{head.lstrip('# ')} ({writer.replace('Writer: ', '')}): "
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        end = min(len(text), i + CHUNK)
        if end < len(text):
            cut = text.rfind(". ", i + CHUNK // 2, end)
            end = cut + 1 if cut > 0 else end
        out.append(prefix + text[i:end].strip())
        if end >= len(text):
            break
        i = max(end - OVERLAP, i + 1)
    return out or [prefix]


def _req(method: str, url: str, token: str, data: bytes | None = None, ctype: str = "application/json") -> dict:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"{e.code}: {e.read()[:300]!r}") from e
    return {}


def ensure_index(token: str) -> None:
    try:
        _req("GET", f"{CF}/vectorize/v2/indexes/{INDEX}", token)
    except RuntimeError:
        _req("POST", f"{CF}/vectorize/v2/indexes", token,
             json.dumps({"name": INDEX, "config": {"dimensions": DIMS, "metric": "cosine"},
                         "description": "viapatrum.org passages (qwen3-embedding-0.6b)"}).encode())
        print(f"created index {INDEX}")


def embed_docs(token: str, texts: list[str]) -> list[list[float]]:
    res = _req("POST", f"{CF}/ai/run/{EMBED}", token, json.dumps({"documents": texts}).encode())
    return (res.get("result") or {}).get("data") or []


def upload() -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("no CLOUDFLARE_API_TOKEN", file=sys.stderr)
        return 2
    ensure_index(token)
    state_path = DOCS / ".uploaded.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    docs = sorted(DOCS.glob("*.md"))
    pending, stale_ids = [], []   # (key, sha, chunk_no, text)
    for path in docs:
        body = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(body.encode()).hexdigest()
        if state.get(path.name, {}).get("sha") == sha:
            continue
        stale_ids += state.get(path.name, {}).get("ids", [])
        for n, c in enumerate(chunks(body)):
            pending.append((path.name, sha, n, c))
    live = {p.name for p in docs}
    for name in [k for k in state if k not in live]:
        stale_ids += state.pop(name).get("ids", [])
    print(f"{len(pending)} chunks to embed, {len(stale_ids)} stale vectors", flush=True)
    for i in range(0, len(stale_ids), 100):  # API max 100 ids per delete
        _req("POST", f"{CF}/vectorize/v2/indexes/{INDEX}/delete_by_ids", token,
             json.dumps({"ids": stale_ids[i:i + 100]}).encode())
    new_ids: dict[str, list] = {}
    shas: dict[str, str] = {}
    failed = 0
    from concurrent.futures import ThreadPoolExecutor
    import threading
    lock = threading.Lock()

    def one(batch):
        vecs = embed_docs(token, [c[3] for c in batch])
        if len(vecs) != len(batch):
            raise RuntimeError(f"got {len(vecs)} vectors for {len(batch)} chunks")
        lines, ids = [], []
        for (key, sha, n, text), v in zip(batch, vecs):
            vid = hashlib.sha1(key.encode()).hexdigest()[:24] + f"-{n}"
            lines.append(json.dumps({"id": vid, "values": v, "metadata": {"k": key, "t": text[:3000]}}))
            ids.append((key, sha, vid))
        _req("POST", f"{CF}/vectorize/v2/indexes/{INDEX}/upsert", token, ("\n".join(lines)).encode(), "application/x-ndjson")
        return ids

    # Network-bound: 8 batches in flight (2026-10-03: serial ran ~170 chunks/min).
    batches = [pending[b:b + 32] for b in range(0, len(pending), 32)]
    done = 0
    with ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(one, bt): bt for bt in batches}
        for fu in futs:
            try:
                for key, sha, vid in fu.result():
                    with lock:
                        new_ids.setdefault(key, []).append(vid)
                        shas[key] = sha
            except Exception as e:
                failed += 1
                for key, *_ in futs[fu]:
                    new_ids.pop(key, None)
                    shas.pop(key, None)
                if failed <= 5:
                    print(f"batch failed: {e}", file=sys.stderr, flush=True)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(batches)} batches", flush=True)
                for key, ids in new_ids.items():
                    if key in shas:
                        state[key] = {"sha": shas[key], "ids": ids}
                state_path.write_text(json.dumps(state))
    for key, ids in new_ids.items():
        if key in shas:
            state[key] = {"sha": shas[key], "ids": ids}
    state_path.write_text(json.dumps(state))
    print(f"upload done: {len(state)} documents indexed, {failed} failed batches")
    return 1 if failed else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"export": export, "upload": upload}.get(cmd, lambda: (print(__doc__), 2)[1])())
