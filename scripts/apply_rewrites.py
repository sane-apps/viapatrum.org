#!/usr/bin/env python3
"""Apply cross-verified rewrite agreements to translations (dry-run default).

Only applies when the agreed quote matches EXACTLY ONE span inside ONE english
list element of the passage file (whitespace-normalized). Zero or ambiguous
matches, cross-element spans, and drifted text go to the manual queue.
Every applied edit is recorded for audit. DRY RUN unless --apply.

Usage:
  python3 apply_rewrites.py --agreements outputs/prose-audit/verify-llama.json
      --out outputs/prose-audit/applied.json [--apply]
"""
import argparse, difflib, hashlib, json, os, sys, re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_rewrites import load_sections_full
from prose_audit import chunk_hash

WS = re.compile(r"\s+")
INDENT = 2  # translations *_english.json use 2-space indent (verified 2026-10-02)


def norm_index_map(raw):
    """Collapse whitespace runs; return (normalized, raw_index_per_norm_char)."""
    out, mp = [], []
    i, n = 0, len(raw)
    while i < n:
        if raw[i].isspace():
            j = i
            while j < n and raw[j].isspace():
                j += 1
            # keep a single space unless at a boundary we trim
            if out and j < n:
                out.append(" ")
                mp.append(i)
            i = j
        else:
            out.append(raw[i])
            mp.append(i)
            i += 1
    return "".join(out), mp


PUNCT = re.compile(r"[^\w\s]")


def _variants(quote):
    nq = WS.sub(" ", quote).strip()
    yield "exact", nq
    yield "casefold", nq.casefold()
    yield "nopunct", PUNCT.sub("", nq.casefold())


def find_spans(raw, quote):
    """All (start, end) raw offsets where quote occurs.

    Fallback cascade (exact -> casefold -> punctuation-stripped); first level
    with any match wins. Uniqueness is still required by the caller, so loose
    matching never causes an ambiguous replace.
    """
    nt, mp = norm_index_map(raw)
    cands = {"exact": nt, "casefold": nt.casefold(),
             "nopunct": PUNCT.sub("", nt.casefold())}
    for level, nq in _variants(quote):
        if not nq:
            continue
        hay = cands[level]
        # map haystack offsets back through punctuation stripping
        if level == "nopunct":
            keep = [i for i, ch in enumerate(nt.casefold())
                    if ch.isalnum() or ch == "_" or ch.isspace()]
            if len(keep) != len(hay):
                continue
        spans = []
        at = 0
        while True:
            k = hay.find(nq, at)
            if k < 0:
                break
            at = k + 1
            # token boundary: match must not sit inside a larger alnum run
            if k > 0 and hay[k - 1].isalnum() and nq[0].isalnum():
                continue
            e = k + len(nq)
            if e < len(hay) and hay[e].isalnum() and nq[-1].isalnum():
                continue
            if level == "nopunct":
                spans.append((mp[keep[k]], mp[keep[k + len(nq) - 1]] + 1))
            else:
                spans.append((mp[k], mp[k + len(nq) - 1] + 1))
        if spans:
            return spans
    return []


def apply_spans(el, spans, rw):
    """Replace spans (raw offsets) with rw, latest-first. Empty rw deletes the
    span and collapses leftover whitespace."""
    for st, en in sorted(spans, reverse=True):
        el = el[:st] + rw + el[en:]
    if not rw.strip():
        el = re.sub(r" {2,}", " ", el).strip()
    return el


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agreements", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--suggestions", default=None,
                    help="rewrites file carrying text_hash (staleness check)")
    ap.add_argument("--skip-applied", default=None,
                    help="prior applied.json: skip items already applied")
    ap.add_argument("--exclude-keys", default="",
                    help="comma-separated keys to skip (reviewer veto)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--orchestrator", action="store_true",
                    help="allow verdict=orchestrator pairs past the overlap gate "
                         "(pairing verified by orchestrator vs witness; all other guards stay)")
    a = ap.parse_args()
    rep = json.load(open(a.agreements))["agreements"]
    result = {"applied": [], "manual": [], "files_touched": {}}
    seen = set()
    cache = {}
    snap = {}  # compare-and-swap: raw bytes at load
    sug_hashes = {}
    if a.suggestions and os.path.isfile(a.suggestions):
        try:
            for k, e in json.load(open(a.suggestions)).get("suggestions", {}).items():
                if e.get("text_hash"):
                    sug_hashes[k] = e["text_hash"]
        except Exception:
            pass
    done_before = set()
    if a.skip_applied and os.path.isfile(a.skip_applied):
        try:
            for x in json.load(open(a.skip_applied)).get("applied", []):
                done_before.add((x.get("key"), (x.get("quote") or "")[:120]))
        except Exception:
            pass
    excluded = set(k.strip() for k in a.exclude_keys.split(",") if k.strip())
    for key in sorted(rep):
        if key in excluded:
            result.setdefault("skipped_veto", []).append({"key": key})
            continue
        slug, at = key.rsplit("@", 1)
        secs = load_sections_full(slug)
        chunk = secs[int(at):int(at) + 3]
        if key in sug_hashes and sug_hashes[key] != chunk_hash(chunk):
            result["manual"].append({"key": key, "why": "stale (text changed since draft)"})
            continue
        if not chunk:
            result["manual"].append({"key": key, "why": "chunk-empty"})
            continue
        for item in rep[key]["agreed"]:
            q, rw = item["quote"], item["rewrite"]
            if (key, q[:120]) in done_before:
                result.setdefault("skipped_done", []).append({"key": key})
                continue
            nq, nrw = WS.sub(" ", q).strip(), WS.sub(" ", rw).strip()
            orch_ok = a.orchestrator and item.get("verdict") == "orchestrator"
            if nrw and not orch_ok and difflib.SequenceMatcher(None, nq, nrw).ratio() < 0.4:
                result["manual"].append({"key": key, "quote": q[:120],
                                         "why": "rewrite unrelated to quote"})
                continue
            if not nrw and len(nq.split()) > 12:
                result["manual"].append({"key": key, "quote": q[:120],
                                         "why": "long deletion needs eyes"})
                continue
            sig = (key, nq, nrw)
            if sig in seen:
                result.setdefault("skipped_dup", []).append({"key": key})
                continue
            seen.add(sig)
            if WS.sub(" ", q).strip() == WS.sub(" ", rw).strip():
                result.setdefault("skipped_noop", []).append({"key": key, "quote": q[:120]})
                continue
            # gather candidate (file, rowidx, elemidx, raw, spans) across chunk files
            cands = []
            for s in chunk:
                f = s["file"]
                if f not in cache:
                    raw = open(f, "rb").read()
                    cache[f] = json.loads(raw)
                    snap[f] = hashlib.sha256(raw).hexdigest()
                rows = cache[f]
                rows = rows if isinstance(rows, list) else rows.get("english", [])
                if isinstance(rows, dict):
                    rows = rows.get("sections", [])
                for ri, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    eng = row.get("english", [])
                    elems = eng if isinstance(eng, list) else [eng]
                    for ei, el in enumerate(elems):
                        if not isinstance(el, str):
                            continue
                        spans = find_spans(el, q)
                        if spans:
                            cands.append((f, ri, ei, el, spans))
            if not cands:
                result["manual"].append({"key": key, "quote": q[:120], "why": "0 matches"})
                continue
            # Multi-occurrence rule: all matched spans must normalize identically
            # (same sentence repeated/refrain/overlap). The verifier agreed on this
            # chunk, so the agreement covers every same-chunk occurrence.
            groups = defaultdict(list)
            for f, ri, ei, el, spans in cands:
                for st, en in spans:
                    groups[WS.sub(" ", el[st:en]).strip()].append((f, ri, ei, el, st, en))
            groups.pop(WS.sub(" ", rw).strip(), None)
            if len(groups) == 0:
                result.setdefault("skipped_done", []).append({"key": key, "why": "already reads as rewrite"})
                continue
            if len(groups) != 1:
                result["manual"].append({"key": key, "quote": q[:120],
                                         "why": f"{len(cands)} elems, {len(groups)} variants left"})
                continue
            [(kept_text, locs)] = groups.items()
            by_elem = defaultdict(list)
            for f, ri, ei, el, st, en in locs:
                by_elem[(f, ri, ei, el)].append((st, en))
            cands = [(f, ri, ei, el, sp) for (f, ri, ei, el), sp in by_elem.items()]
            n_spans = sum(len(sp) for _, _, _, _, sp in cands)
            result["applied"].append({"key": key, "quote": q, "rewrite": rw,
                                      "occurrences": n_spans,
                                      "files": sorted(set(f for f, _, _, _, _ in cands))})
            for f, ri, ei, el, spans in cands:
                new_el = apply_spans(el, spans, rw)
                rows = cache[f]
                rows = rows if isinstance(rows, list) else rows.get("english", [])
                if isinstance(rows, dict):
                    rows = rows.get("sections", [])
                row = rows[ri]
                if isinstance(row.get("english"), list):
                    row["english"][ei] = new_el
                else:
                    row["english"] = new_el
                result["files_touched"][f] = result["files_touched"].get(f, 0) + 1
    if a.apply:
        for f, top in cache.items():
            if f in result["files_touched"]:
                # CAS: another writer (e.g. overnight pipeline) touched this
                # file mid-run -> skip the write, requeue items, never clobber.
                try:
                    cur = hashlib.sha256(open(f, "rb").read()).hexdigest()
                except Exception:
                    cur = None
                if cur != snap.get(f):
                    keep = []
                    for x in result["applied"]:
                        if f in x.get("files", []):
                            result["manual"].append(
                                {"key": x["key"], "quote": x["quote"][:120],
                                 "why": "file changed during apply (concurrent writer); retry"})
                        else:
                            keep.append(x)
                    result["applied"] = keep
                    continue
                json.dump(top, open(f, "w"), indent=INDENT, ensure_ascii=False)
                open(f, "a").write("\n")
    json.dump(result, open(a.out, "w"), indent=1)
    print(f"{'APPLIED' if a.apply else 'DRY-RUN'}: {len(result['applied'])} applied, "
          f"{len(result['manual'])} manual, {len(result['files_touched'])} files, "
          f"{len(result.get('skipped_done', []))} already-done, "
          f"{len(result.get('skipped_dup', []))} dups, "
          f"{len(result.get('skipped_noop', []))} noops")


if __name__ == "__main__":
    main()
