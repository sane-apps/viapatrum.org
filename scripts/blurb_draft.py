#!/usr/bin/env python3
"""Draft work-list teasers for books missing blurbs (Qwen, CF Workers AI).

Suggestions ONLY - output is reviewed before anything is written to _meta.json.
Usage:
  SANE_LLM_API_RECEIPT=... CLOUDFLARE_API_TOKEN=... python3 blurb_draft.py \
      --slugs slug1,slug2 --out outputs/prose-audit/blurb-drafts.json
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.expanduser("~"), "SaneApps/infra/SaneProcess/scripts"))
from llm_vendor_gate import require_llm_receipt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prose_audit import load_sections, cf_call

BOOKS = os.path.join(os.path.expanduser("~"), "SaneApps/clients/translations/books")
SYSTEM = """You write one-line catalogue teasers for a public library of ancient Christian texts.
Given a work's author, title, and opening lines, reply with ONE JSON object only, no fences:
{"teaser": "<ONE enticing sentence, <=170 characters>"}
Rules: say what the work IS and why a normal reader would open it. Plain modern
words. No dates, no section counts, no catalogue IDs, no TODO/scope notes, no
Greek without gloss, no em dashes. Never restate just "Author - Title"."""

def title_author(slug):
    yml = os.path.join(BOOKS, slug, "book.yml")
    title, author = slug, ""
    try:
        for line in open(yml):
            s = line.strip()
            if s.startswith("title:"):
                title = s.split(":", 1)[1].strip().strip("'\"")
            elif s.startswith("author:"):
                author = s.split(":", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return title, author

def main():
    sys.exit("RETIRED 2026-10-02 (SOP role boundary): CF models translate ONLY — "
                 "never draft factual copy. Author blurbs directly with sources.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", required=True)
    ap.add_argument("--model", default="@cf/qwen/qwen3-30b-a3b-fp8")
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm-api-receipt", default=None)
    a = ap.parse_args()
    require_llm_receipt([a.model], receipt_path=a.llm_api_receipt)
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("need CLOUDFLARE_API_TOKEN")
    out = {}
    if os.path.isfile(a.out):
        try:
            out = json.load(open(a.out))
        except Exception:
            out = {}
    slugs = [s.strip() for s in a.slugs.split(",") if s.strip()]
    for slug in slugs:
        if slug in out and out[slug].get("teaser"):
            continue
        title, author = title_author(slug)
        secs = load_sections(slug)
        opening = "\n".join(s["text"][:600] for s in secs[:2])
        user = f"Author: {author}\nTitle: {title}\nOpening lines:\n{opening}"
        r = cf_call(a.model, user, token, timeout=90, system=SYSTEM)
        if "error" in r:
            out[slug] = {"error": r["error"]}
            continue
        try:
            c = r["content"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            j, _ = json.JSONDecoder().raw_decode(c)
            out[slug] = {"title": title, "author": author, "teaser": j["teaser"]}
        except Exception:
            out[slug] = {"title": title, "author": author, "error": "unparseable",
                         "raw": r.get("content", "")[:200]}
        json.dump(out, open(a.out, "w"), indent=1)
        print("drafted", slug, flush=True)
    n = sum(1 for v in out.values() if v.get("teaser"))
    print(f"blurb drafts: {n}/{len(slugs)}")

if __name__ == "__main__":
    main()
