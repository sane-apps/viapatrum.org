"""Conservative public-catalogue checks for unmistakable draft scaffolding.

Passing this check does not establish translation fidelity or completeness.
"""
from __future__ import annotations

import re

# Match the generated scaffold phrases, not legitimate discussion of a lemma.
SCAFFOLD = re.compile(
    r"\blemma-led\s+open\b|\brem\s+(?:early|mid|closeout)\s*:|"
    r"\blemma and argument toward the thesis\b",
    re.I,
)


# Exact contamination found in alleged Latin copy-texts; not a language heuristic.
SOURCE_CONTAMINATION = re.compile(
    r"\btemporary\b|\bMelito skipped\b|\bnever Cyril Matthew densify\b", re.I
)


# Editorial hold, 2026-09-13: named whole books/homilies contain only 44–186
# English words, with summary-like sources; see docs/IA.md audit and
# outputs/catalogue-audit/short-whole-work-review.json. These need source
# review, not a claim that every short ancient text is invalid.
SCOPE_REVIEW_HOLD = frozenset({
    'origen-contra-celsum-book-2',
    'origen-contra-celsum-book-3',
    'origen-contra-celsum-book-4',
    'origen-contra-celsum-book-5',
    'origen-contra-celsum-book-6',
    'origen-contra-celsum-book-7',
    'origen-contra-celsum-book-8',
    'origen-de-principiis-book-2',
    'origen-de-principiis-book-3',
    'origen-de-principiis-book-4',
    'origen-exodus-homily-10',
    'origen-exodus-homily-11',
    'origen-exodus-homily-12',
    'origen-exodus-homily-13',
    'origen-exodus-homily-9',
    'origen-ezekiel-homily-1',
    'origen-ezekiel-homily-10',
    'origen-ezekiel-homily-11',
    'origen-ezekiel-homily-12',
    'origen-ezekiel-homily-13',
    'origen-ezekiel-homily-14',
    'origen-ezekiel-homily-2',
    'origen-ezekiel-homily-3',
    'origen-ezekiel-homily-4',
    'origen-ezekiel-homily-5',
    'origen-ezekiel-homily-6',
    'origen-ezekiel-homily-7',
    'origen-ezekiel-homily-8',
    'origen-ezekiel-homily-9',
    'origen-genesis-homily-11',
    'origen-genesis-homily-12',
    'origen-genesis-homily-13',
    'origen-genesis-homily-14',
    'origen-genesis-homily-15',
    'origen-genesis-homily-16',
    'origen-genesis-homily-5',
    'origen-genesis-homily-6',
    'origen-genesis-homily-7',
    'origen-genesis-homily-8',
    'origen-genesis-homily-9',
    'origen-isaiah-homily-2',
    'origen-isaiah-homily-3',
    'origen-isaiah-homily-4',
    'origen-isaiah-homily-5',
    'origen-isaiah-homily-6',
    'origen-isaiah-homily-7',
    'origen-isaiah-homily-8',
    'origen-isaiah-homily-9',
    'origen-joshua-homily-10',
    'origen-joshua-homily-11',
    'origen-joshua-homily-12',
    'origen-joshua-homily-13',
    'origen-joshua-homily-14',
    'origen-joshua-homily-15',
    'origen-joshua-homily-16',
    'origen-joshua-homily-17',
    'origen-joshua-homily-18',
    'origen-joshua-homily-19',
    'origen-joshua-homily-20',
    'origen-joshua-homily-21',
    'origen-joshua-homily-22',
    'origen-joshua-homily-23',
    'origen-joshua-homily-24',
    'origen-joshua-homily-25',
    'origen-joshua-homily-26',
    'origen-joshua-homily-7',
    'origen-joshua-homily-8',
    'origen-joshua-homily-9',
    'origen-judges-homily-2',
    'origen-judges-homily-3',
    'origen-judges-homily-4',
    'origen-judges-homily-5',
    'origen-judges-homily-6',
    'origen-judges-homily-7',
    'origen-judges-homily-8',
    'origen-judges-homily-9',
    'origen-leviticus-homily-10',
    'origen-leviticus-homily-11',
    'origen-leviticus-homily-12',
    'origen-leviticus-homily-13',
    'origen-leviticus-homily-14',
    'origen-leviticus-homily-15',
    'origen-leviticus-homily-16',
    'origen-leviticus-homily-2',
    'origen-leviticus-homily-6',
    'origen-leviticus-homily-7',
    'origen-numbers-homily-1',
    'origen-numbers-homily-10',
    'origen-numbers-homily-11',
    'origen-numbers-homily-12',
    'origen-numbers-homily-13',
    'origen-numbers-homily-14',
    'origen-numbers-homily-15',
    'origen-numbers-homily-16',
    'origen-numbers-homily-17',
    'origen-numbers-homily-18',
    'origen-numbers-homily-19',
    'origen-numbers-homily-20',
    'origen-numbers-homily-21',
    'origen-numbers-homily-22',
    'origen-numbers-homily-23',
    'origen-numbers-homily-24',
    'origen-numbers-homily-25',
    'origen-numbers-homily-26',
    'origen-numbers-homily-27',
    'origen-numbers-homily-28',
    'origen-numbers-homily-8',
    'origen-numbers-homily-9',
    'origen-psalm-36-homily-1',
    'origen-psalm-36-homily-2',
    'origen-psalm-36-homily-3',
    'origen-psalm-36-homily-4',
    'origen-psalm-36-homily-5',
    'origen-psalm-37-homily-1',
    'origen-psalm-37-homily-2',
    'origen-psalm-38-homily-1',
    'origen-psalm-38-homily-2',
    'origen-romans-book-10',
    'origen-romans-book-2',
    'origen-romans-book-3',
    'origen-romans-book-4',
    'origen-romans-book-5',
    'origen-romans-book-6',
    'origen-romans-book-7',
    'origen-romans-book-8',
    'origen-romans-book-9',
})


# Named editorial holds from source/body inspection, not a global length rule.
EXTENDED_REVIEW_HOLD = {
    'cyril-trinity-dialogue-1': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'cyril-trinity-dialogue-2': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'cyril-trinity-dialogue-3': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'cyril-trinity-dialogue-4': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'cyril-trinity-dialogue-5': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'cyril-trinity-dialogue-6': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'cyril-trinity-dialogue-7': 'Dialogue presented as complete with only opening/remainder slices; full source coverage unverified in contaminated dialogue series.',
    'origen-contra-celsum-book-1': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-contra-celsum-preface': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-de-principiis': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-exodus-homily-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-2': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-3': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-4': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-5': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-6': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-7': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-exodus-homily-8': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-genesis-homily-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-genesis-homily-2': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-genesis-homily-3': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-genesis-homily-4': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-isaiah-homily-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-john-13': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-john-19': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-john-20': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-john-28': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-john-32': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-joshua-homily-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-joshua-homily-2': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-joshua-homily-3': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-joshua-homily-4': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-joshua-homily-5': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-joshua-homily-6': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-judges-homily-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-leviticus-homily-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-leviticus-homily-3': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-leviticus-homily-4': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-leviticus-homily-5': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-leviticus-homily-8': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-leviticus-homily-9': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-luke-homilies': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-matthew-series': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-matthew-tomus-15': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-matthew-tomus-16': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-matthew-tomus-17': 'Sampled source blocks or third-person summaries presented as full work/series; section-range coverage and reading translation require source review.',
    'origen-numbers-homily-2': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-numbers-homily-4': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-numbers-homily-5': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-numbers-homily-6': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-numbers-homily-7': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-romans-book-1': 'Condensed homily/commentary family: very short source and English sections presented as complete; exact edition alignment requires review after confirmed Genesis X source mismatch.',
    'origen-song-commentary-liber-1': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-song-commentary-liber-2': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-song-commentary-liber-3': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
    'origen-song-commentary-prologus': 'Condensed source family: claimed complete books have brief paraphrase-like Greek/Latin sections; exact edition alignment unverified. Song IV has confirmed operational-text contamination.',
}


def text_value(value) -> str:
    if isinstance(value, list):
        return " ".join(str(part) for part in value)
    return str(value or "")


def partition_catalogue(works: list[dict]) -> tuple[list[dict], list[dict]]:
    """Hold entire mixed works; preserve every source and translation file."""
    if len({work["slug"] for work in works}) != len(works):
        raise ValueError("Merge duplicate work slugs before applying catalogue quality checks")
    readable, held = [], []
    for work in works:
        findings = []
        if not work.get("sections"):
            findings.append({"section": None, "reason": "empty_work"})
        if work["slug"] in EXTENDED_REVIEW_HOLD:
            findings.append({
                "section": None,
                "reason": "source_scope_requires_review",
                "excerpt": EXTENDED_REVIEW_HOLD[work["slug"]],
            })
        if work["slug"] in SCOPE_REVIEW_HOLD:
            findings.append({
                "section": None,
                "reason": "whole_work_scope_requires_source_review",
                "excerpt": work.get("blurb", "")[:240],
            })
        for section in work.get("sections", []):
            english = text_value(section.get("english"))
            latin = text_value(section.get("latin"))
            contamination = SOURCE_CONTAMINATION.search(latin)
            if contamination:
                findings.append({
                    "section": str(section.get("section")),
                    "reason": "source_contamination",
                    "matched": contamination.group(0),
                    "excerpt": latin[:240],
                })
                continue
            match = SCAFFOLD.search(english)
            if not english.strip():
                findings.append({"section": str(section.get("section")), "reason": "empty_english"})
            elif match:
                findings.append({
                    "section": str(section.get("section")),
                    "reason": "draft_scaffold",
                    "matched": match.group(0),
                    "excerpt": english[:240],
                })
        if findings:
            held.append({
                "slug": work["slug"],
                "title": work.get("title", ""),
                "author": work.get("author", ""),
                "section_count": len(work.get("sections", [])),
                "flagged_section_count": len(findings),
                "findings": findings,
            })
        else:
            readable.append(work)
    return readable, held



def publication_inventory(works, excerpts):
    """Identity and complete reader payload bind the provisional legacy baseline."""
    entries = {}
    for work in works:
        for row in work["sections"]:
            key = f"work:{work['slug']}:{row['section']}"
            if key in entries:
                raise ValueError(f"Duplicate public identity: {key}")
            entries[key] = {"author": work["author"], "work": work["title"], "row": row}
    for row in excerpts:
        key = f"excerpt:{row['id']}"
        if key in entries:
            raise ValueError(f"Duplicate public identity: {key}")
        entries[key] = {"author": row.get("author"), "work": row.get("work"), "row": row}
    return entries


def publication_digest(value):
    import hashlib
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def work_scope(work):
    """Reader identity, source disclosures and ordered extent are reviewed together."""
    return {**{k: v for k, v in work.items() if k != "sections"},
            "section_ids": [str(row["section"]) for row in work.get("sections", [])]}


def check_publication(works, excerpts, root, corpus):
    """Freeze legacy rows/scope; new content needs current source review, not status."""
    import json
    import sys
    manifest = json.loads((root / "data/publication-review.json").read_text())
    if manifest.get("schema") != "fathers-publication-v1":
        raise ValueError("Missing publication review schema")
    legacy = manifest["provisional_legacy"]
    reviews = manifest.get("reviews", {})
    entries = publication_inventory(works, excerpts)
    if str(corpus) not in sys.path:
        sys.path.insert(0, str(corpus))
    from pipeline.check_pass_ab import content_errors
    from pipeline.verify_translation_qa import validate_audit_receipt
    failures, packets = {}, {}

    def reviewed_packet(index):
        pair = (index["packet"], index["receipt"])
        if pair not in packets:
            paths = [(corpus / name).resolve() for name in pair]
            if any(not path.is_relative_to(corpus.resolve()) for path in paths):
                raise ValueError("Review files must stay in the corpus")
            packet, receipt = (json.loads(path.read_text()) for path in paths)
            errors = validate_audit_receipt(packet, receipt)
            selected = {item["section"]: item for item in packet.get("sections", [])} if not errors else {}
            # Regenerate/hash once per pair, not once per reviewed section.
            packets[pair] = (packet, selected, errors)
        return packets[pair]

    def identity_errors(packet, author, title, edition):
        identity = packet.get("identity") or {}
        expected = {"author": author, "work": title, "edition": edition}
        return [f"reviewed identity {key} does not match the publication"
                for key, value in expected.items() if not value or identity.get(key) != value]

    exception_types = (OSError, ValueError, KeyError, TypeError, AttributeError)
    works_by_slug = {work["slug"]: work for work in works}
    # Publish plan per work: the reviewed leading prefix of its sections.
    # A clean reviewed prefix publishes (tail held, never public); anything
    # else (reorder, drop, middle edit, metadata change) holds the whole work.
    publish_ids = {}
    for work in works:
        key = f"work:{work['slug']}:@scope"
        scope = work_scope(work)
        if not scope["section_ids"]:
            failures[key] = ["empty work"]
            continue
        if manifest.get("provisional_work_scopes", {}).get(work["slug"]) == publication_digest(scope):
            publish_ids[work["slug"]] = [str(i) for i in scope["section_ids"]]
            continue
        try:
            index = manifest.get("scope_reviews", {}).get(work["slug"])
            if not isinstance(index, dict):
                raise ValueError("new or changed work extent/metadata has no source scope review")
            packet, _selected, errors = reviewed_packet(index)
            errors = list(errors) + identity_errors(packet, work.get("author"), work.get("title"), work.get("edition"))
            reviewed = packet.get("publication_scope")
            if not isinstance(reviewed, dict):
                errors.append("reviewed scope does not match current metadata and ordered sections")
            else:
                meta_now = {k: v for k, v in scope.items() if k != "section_ids"}
                meta_was = {k: v for k, v in reviewed.items() if k != "section_ids"}
                reviewed_ids = [str(i) for i in reviewed.get("section_ids", [])]
                current_ids = [str(i) for i in scope["section_ids"]]
                if meta_now != meta_was or not reviewed_ids:
                    errors.append("reviewed scope does not match current metadata and ordered sections")
                elif current_ids[:len(reviewed_ids)] != reviewed_ids:
                    errors.append("reviewed scope is not a leading prefix of current sections")
                else:
                    publish_ids[work["slug"]] = list(reviewed_ids)
            if errors:
                failures[key] = errors
        except exception_types as exc:
            failures[key] = [f"unusable scope review: {exc}"]

    tails = {}
    for key, payload in entries.items():
        row = payload["row"]
        slug = key.split(":", 2)[1] if key.startswith("work:") else None
        sec = key.split(":", 2)[2] if key.startswith("work:") else None
        tail_hold = (slug is not None and slug in publish_ids
                     and f"work:{slug}:@scope" not in failures
                     and str(sec) not in {str(i) for i in publish_ids[slug]})

        def record(errs):
            if tail_hold:
                tails.setdefault(slug, []).append({"section": sec, "errors": list(errs)})
            else:
                failures[key] = list(errs)

        issues = content_errors(text_value(row.get("english")))
        if issues:
            record(issues)
            continue
        if legacy.get(key) == publication_digest(payload):
            continue
        index = reviews.get(key)
        if not isinstance(index, dict):
            record(["new or changed passage has no source review"])
            continue
        try:
            packet, selected, errors = reviewed_packet(index)
            errors = list(errors)
            work = works_by_slug.get(key.split(":", 2)[1]) if key.startswith("work:") else None
            edition = work.get("edition") if work else (row.get("edition_id") or row.get("edition"))
            errors += identity_errors(packet, payload["author"], payload["work"], edition)
            item = selected.get(str(index["section"]))
            if not item:
                errors.append("section was not selected and reviewed")
            else:
                source = row.get("greek") or row.get("latin") or row.get("source_text")
                if source != item["source_text"] or row.get("english") != item["english"]:
                    errors.append("consumer source or English differs from the reviewed passage")
                locus = str(row.get("locus") or row.get("location") or row.get("section") or row.get("id"))
                if locus != str(item.get("locus")):
                    errors.append("consumer locus differs from reviewed source locus")
            if index.get("payload_sha256") != publication_digest(payload):
                errors.append("review index does not bind current identity and reader payload")
            if errors:
                record(errors)
        except exception_types as exc:
            record([f"unusable review: {exc}"])
    bad_works = {key.split(":", 2)[1] for key in failures if key.startswith("work:")}
    held = [{"slug": w["slug"], "title": w["title"], "author": w["author"],
             "section_count": len(w["sections"]), "reason": "publication_review_required",
             "findings": [{"section": key.split(":", 2)[2], "reason": "publication_review_required",
                           "errors": errors} for key, errors in failures.items()
                          if key.startswith(f"work:{w['slug']}:")]}
            for w in works if w["slug"] in bad_works]
    kept = []
    tail_records = []
    for w in works:
        if w["slug"] in bad_works:
            continue
        plan = publish_ids.get(w["slug"])
        current_ids = [str(r["section"]) for r in w["sections"]]
        if plan is None or [str(i) for i in plan] == current_ids:
            kept.append(w)
            continue
        pubset = {str(i) for i in plan}
        trimmed = [r for r in w["sections"] if str(r["section"]) in pubset]
        if [str(r["section"]) for r in trimmed] != [str(i) for i in plan] or not trimmed:
            failures[f"work:{w['slug']}:@scope"] = ["publish prefix diverged; holding whole work"]
            held.append({"slug": w["slug"], "title": w["title"], "author": w["author"],
                         "section_count": len(w["sections"]), "reason": "publication_review_required",
                         "findings": [{"section": "@scope", "reason": "publication_review_required",
                                       "errors": failures[f"work:{w['slug']}:@scope"]}]})
            bad_works.add(w["slug"])
            continue
        out = dict(w)
        out["sections"] = trimmed
        kept.append(out)
        held_ids = [i for i in current_ids if i not in pubset]
        findings = list(tails.get(w["slug"], []))
        known = {str(f["section"]) for f in findings}
        for i in held_ids:
            if i not in known:
                findings.append({"section": i, "errors": ["beyond reviewed scope"]})
        tail_records.append({"slug": w["slug"], "title": w["title"], "author": w["author"],
                             "published_sections": len(trimmed),
                             "held_sections": [f["section"] for f in findings],
                             "reason": "unreviewed_tail", "findings": findings})
    return (kept,
            [x for x in excerpts if f"excerpt:{x['id']}" not in failures], held, failures,
            tail_records)


def self_check() -> None:
    def work(slug, *bodies):
        return {"slug": slug, "sections": [
            {"section": i, "english": body} for i, body in enumerate(bodies, 1)
        ]}
    good = work("good", ["He explains the lemma before the argument."])
    mixed = work("mixed", ["A real translated paragraph."], ["Rem early: Unit 1; lemma and argument toward the thesis."])
    drafts = work("drafts", ["Lemma-led open — Greek"], ["Rem CLOSEOUT: Unit 1 CLOSEOUT."])
    empty = work("empty", [])
    original = mixed["sections"][0]["english"][:]
    kept, held = partition_catalogue([good, mixed, drafts, empty])
    assert kept == [good]
    try:
        partition_catalogue([good, good])
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate work slugs must be merged before quality checks")
    assert partition_catalogue([work("origen-contra-celsum-book-2", ["Summary."])])[1]
    assert partition_catalogue([work("genuine-short-fragment", ["One surviving sentence."])])[0]
    assert [row["slug"] for row in held] == ["mixed", "drafts", "empty"]
    assert [row["flagged_section_count"] for row in held] == [1, 2, 1]
    assert mixed["sections"][0]["english"] == original
    contaminated = work("contaminated", ["A reading paragraph."])
    contaminated["sections"][0]["latin"] = ["Profanus qui pro cibo temporary primatum spiritus vendit."]
    assert partition_catalogue([contaminated])[1][0]["findings"][0]["reason"] == "source_contamination"


if __name__ == "__main__":
    self_check()
    print("catalogue_quality: checks passed")
