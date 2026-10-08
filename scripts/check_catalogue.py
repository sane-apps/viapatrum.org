"""Focused catalogue regression checks; run with the translations Python."""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
import build_site as site
from catalogue_quality import self_check, check_publication, publication_inventory, publication_digest, work_scope

self_check()

# A legacy hash is not a review. Changed text with no review entry is held too.
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "data").mkdir()
    corpus = site.BOOKS.parent
    row = {"id": "fixture", "author": "A", "work": "W", "english": ["A reading passage."]}
    manifest = {"schema": "fathers-publication-v1", "provisional_legacy": {
        key: publication_digest(value) for key, value in publication_inventory([], [row]).items()},
        "reviews": {}}
    (root / "data/publication-review.json").write_text(json.dumps(manifest))
    legacy = check_publication([], [row], root, corpus)
    assert not legacy[1] and any("legacy hash is not a review" in e for errs in legacy[3].values() for e in errs), legacy[3]
    live_legacy = check_publication([], [row], root, corpus, enforce_review=False)
    assert live_legacy[1] == [row] and not live_legacy[3], live_legacy[3]
    assert any("legacy hash is not a review" in e for errs in live_legacy[5].values() for e in errs)
    changed = {**row, "english": ["A different meaning."]}
    changed_result = check_publication([], [changed], root, corpus)
    assert not changed_result[1] and any("no review entry" in e for errs in changed_result[3].values() for e in errs), changed_result[3]
    manifest["reviews"]["excerpt:fixture"] = {"packet": "../outside.json", "receipt": "none"}
    (root / "data/publication-review.json").write_text(json.dumps(manifest))
    assert check_publication([], [changed], root, corpus)[3]
    scaffold = {**row, "english": ["Lemma-led open — source"]}
    manifest["provisional_legacy"]["excerpt:fixture"] = publication_digest(
        publication_inventory([], [scaffold])["excerpt:fixture"])
    (root / "data/publication-review.json").write_text(json.dumps(manifest))
    assert not check_publication([], [scaffold], root, corpus)[1]
    assert not check_publication([], [scaffold], root, corpus, enforce_review=False)[1]

# A mismatched human packet does not hold a content-clean work. One packet
# is still validated once even when it covers several selected passages.
from unittest.mock import patch
from pipeline.verify_translation_qa import make_audit_packet, validate_audit_receipt
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    corpus = root / "corpus"
    corpus.mkdir()
    (root / "data").mkdir()
    english = corpus / "english.json"
    source = corpus / "source.json"
    raw = corpus / "print.txt"
    rows = [{"section": "1", "latin": ["Deus iustos amat."], "english": ["God loves the righteous."]},
            {"section": "2", "latin": ["Nemo cogitur."], "english": ["No one is compelled."]}]
    english.write_text(json.dumps(rows))
    source.write_text(json.dumps(rows))
    raw.write_text("Author A, Work A: Deus iustos amat. Nemo cogitur.")
    work = {"slug": "fixture", "author": "Author A", "title": "Work A", "edition": "Print A",
            "blurb": "Two surviving sections.", "sections": rows}
    identity = {"author": "Author A", "work": "Work A", "edition": "Print A",
                "locus_scheme": "section", "source_url": "https://example.org/print-a"}
    packet = make_audit_packet(english, source, raw_sources=[raw], identity=identity,
                               publication_scope=work_scope(work))
    semantic = {"verdict": "pass", "checks": dict.fromkeys(
        ("source_identity", "completeness", "negation", "agency", "modality", "doctrine", "scripture"), True),
        "uncertainties": [], "covered_source_paragraphs": [1]}
    reviews = [{**semantic, "section": row["section"],
                "notes": f"The print reads {row['latin'][0]} The English reads {row['english'][0]}"}
               for row in rows]
    receipt = {"packet_id": packet["packet_id"], "reviewer": "kimi-k2.6+glm-5.2", "verdict": "pass",
               "reviews": reviews, "scope_review": {**semantic, "notes": reviews[0]["notes"]}}
    (corpus / "packet.json").write_text(json.dumps(packet))
    (corpus / "receipt.json").write_text(json.dumps(receipt))
    pair = {"packet": "packet.json", "receipt": "receipt.json"}
    manifest = {"schema": "fathers-publication-v1", "provisional_legacy": {}, "reviews": {
        key: {**pair, "section": value["row"]["section"], "payload_sha256": publication_digest(value)}
        for key, value in publication_inventory([work], []).items()}, "scope_reviews": {"fixture": pair}}
    manifest_path = root / "data/publication-review.json"
    manifest_path.write_text(json.dumps(manifest))
    with patch("pipeline.verify_translation_qa.validate_audit_receipt", wraps=validate_audit_receipt) as validate:
        kept, _, _, errors, _tails, _deferred = check_publication([work], [], root, corpus)
        assert kept == [work] and not errors, errors
        assert validate.call_count == 1, "same packet rehashed for every passage"
    transplanted = {**work, "author": "Author B", "title": "Work B"}
    for key, value in publication_inventory([transplanted], []).items():
        manifest["reviews"][key]["payload_sha256"] = publication_digest(value)
    manifest["provisional_work_scopes"] = {"fixture": publication_digest(work_scope(transplanted))}
    manifest_path.write_text(json.dumps(manifest))
    assert check_publication([transplanted], [], root, corpus)[0], "content-clean work was held for a mismatched review packet"
    manifest = {"schema": "fathers-publication-v1", "reviews": {},
                "provisional_work_scopes": {"fixture": publication_digest(work_scope(work))},
                "provisional_legacy": {key: publication_digest(value) for key, value in publication_inventory([work], []).items()}}
    manifest_path.write_text(json.dumps(manifest))
    hash_only = check_publication([work], [], root, corpus)
    assert not hash_only[0] and any("no scope review" in e for errs in hash_only[3].values() for e in errs), hash_only[3]
    for changed in ({**work, "sections": rows[:1]}, {**work, "sections": list(reversed(rows))},
                    {**work, "edition": "Another print"}, {**work, "blurb": "Complete works, critically certified"}):
        assert not check_publication([changed], [], root, corpus)[0], "clean change with no review packet was published"
    empty = {**work, "sections": []}
    from catalogue_quality import partition_catalogue
    assert not partition_catalogue([empty])[0], "zero-section work passed catalogue gate"
    assert not check_publication([empty], [], root, corpus)[0], "zero-section work passed publication gate"

    # A matching packet still publishes its reviewed prefix and holds a clean
    # tail the packet did not include. Stale packet drift does not hold the
    # current reading: an edit, a drop, a reorder, or a metadata change publishes.
    scoped_packet = make_audit_packet(english, source, raw_sources=[raw], identity=identity,
                                      expected_sections=["1", "2"], selected_sections=["1", "2"],
                                      publication_scope=work_scope(work))
    scoped_receipt = {"packet_id": scoped_packet["packet_id"], "reviewer": "kimi-k2.6+glm-5.2",
                      "verdict": "pass",
                      "reviews": reviews,
                      "scope_review": {**semantic, "notes": reviews[0]["notes"]}}
    (corpus / "scoped_packet.json").write_text(json.dumps(scoped_packet))
    (corpus / "scoped_receipt.json").write_text(json.dumps(scoped_receipt))
    scoped_pair = {"packet": "scoped_packet.json", "receipt": "scoped_receipt.json"}
    manifest = {"schema": "fathers-publication-v1", "provisional_legacy": {}, "reviews": {
        key: {**scoped_pair, "section": value["row"]["section"],
              "payload_sha256": publication_digest(value)}
        for key, value in publication_inventory([work], []).items()},
        "scope_reviews": {"fixture": scoped_pair}}
    manifest_path.write_text(json.dumps(manifest))
    row3 = {"section": "3", "latin": ["Pax vobiscum."], "english": ["Peace be with you."]}
    english.write_text(json.dumps(rows + [{"section": "3", "english": row3["english"]}]))
    source.write_text(json.dumps(rows + [{"section": "3", "latin": row3["latin"]}]))
    grown = {**work, "sections": rows + [row3]}
    kept, _, _, errors, tails, _deferred = check_publication([grown], [], root, corpus)
    assert kept == [{**work, "sections": rows}], "reviewed head did not publish"
    assert not [k for k in errors if k.startswith("work:")], errors
    assert len(tails) == 1 and tails[0]["held_sections"] == ["3"], tails
    assert tails[0]["published_sections"] == 2
    live_grown = check_publication([grown], [], root, corpus, enforce_review=False)
    assert live_grown[0] and [s["section"] for s in live_grown[0][0]["sections"]] == ["1", "2", "3"], live_grown
    assert not live_grown[4], live_grown[4]
    edited = {**work, "sections": [{**rows[0], "english": ["Changed English."]}, rows[1], row3]}
    kept_edited, _, _, edited_errors, edited_tails, _edited_deferred = check_publication([edited], [], root, corpus)
    assert kept_edited and kept_edited[0]["sections"][0]["english"] == ["Changed English."], edited_errors
    assert not [k for k in edited_errors if k.startswith("work:")], edited_errors
    assert edited_tails and edited_tails[0]["held_sections"] == ["3"], edited_tails
    dropped = {**work, "sections": [rows[0]]}
    kept_dropped = check_publication([dropped], [], root, corpus)[0]
    assert kept_dropped and [s["section"] for s in kept_dropped[0]["sections"]] == ["1"], kept_dropped
    reordered = {**work, "sections": [rows[1], rows[0], row3]}
    kept_reordered = check_publication([reordered], [], root, corpus)[0]
    assert kept_reordered and [s["section"] for s in kept_reordered[0]["sections"]] == ["2", "1", "3"], kept_reordered
    retitled = {**work, "edition": "Another print", "sections": rows + [row3]}
    kept_retitled = check_publication([retitled], [], root, corpus)[0]
    assert kept_retitled and kept_retitled[0]["edition"] == "Another print", kept_retitled
    dirty_tail = {**work, "sections": rows + [{**row3, "english": ["Lemma-led open — source"]}]}
    assert not check_publication([dirty_tail], [], root, corpus, enforce_review=False)[0]
    stamped = json.loads(json.dumps(scoped_receipt))
    stamped["reviewer"] = "cursor-held-eeng-20260924 (Mini)"
    for rev in stamped["reviews"]:
        rev["notes"] = "Pass A/B OET tip."
    stamped["scope_review"]["notes"] = "Engastrimytho tip."
    (corpus / "scoped_receipt.json").write_text(json.dumps(stamped))
    stamped_result = check_publication([work], [], root, corpus)
    stamped_errors = [e for errs in stamped_result[3].values() for e in errs]
    assert not stamped_result[0], stamped_result[3]
    assert any("two model families" in e for e in stamped_errors), stamped_errors
    assert any("do not quote" in e for e in stamped_errors), stamped_errors
    # The live build keeps this reading and records the stamp. The test above
    # still rejects it. A packet outside the corpus stays down either way.
    live_stamp = check_publication([work], [], root, corpus, enforce_review=False)
    assert live_stamp[0] == [work] and not live_stamp[3], live_stamp[3]
    live_stamp_errors = [e for errs in live_stamp[5].values() for e in errs]
    assert any("two model families" in e for e in live_stamp_errors), live_stamp_errors
    assert any("do not quote" in e for e in live_stamp_errors), live_stamp_errors
    manifest = {"schema": "fathers-publication-v1", "reviews": {},
                "provisional_work_scopes": {"fixture": publication_digest(work_scope(work))},
                "provisional_legacy": {key: publication_digest(value)
                                       for key, value in publication_inventory([work], []).items()}}
    manifest_path.write_text(json.dumps(manifest))
    assert not check_publication([work], [], root, corpus)[0]
    live_hash = check_publication([work], [], root, corpus, enforce_review=False)
    assert live_hash[0] == [work] and not live_hash[3], live_hash[3]
    assert any("no scope review" in e for errs in live_hash[5].values() for e in errs), live_hash[5]
    assert not check_publication([{**work, "sections": []}], [], root, corpus, enforce_review=False)[0]
    manifest["scope_reviews"] = {"fixture": {"packet": "../outside.json", "receipt": "none"}}
    manifest_path.write_text(json.dumps(manifest))
    escaped = check_publication([work], [], root, corpus, enforce_review=False)
    assert not escaped[0], escaped[0]
    assert any("must stay in the corpus" in e for errs in escaped[3].values() for e in errs), escaped[3]

kept_w, held_w = site.split_withheld([
    {"slug": "eustathius-engastrimytho", "status": "available"},
    {"slug": "other-work", "status": "available"},
    {"slug": "already-held", "status": "withheld"},
])
assert [w["slug"] for w in kept_w] == ["other-work"], kept_w
assert held_w == ["eustathius-engastrimytho", "already-held"], held_w
eust_meta = json.loads((site.BOOKS / "eustathius-engastrimytho/translations/eeng_u01_open_meta.json").read_text())
assert eust_meta["slug"] == "eustathius-engastrimytho"
assert eust_meta["slug"] in site.FORCED_WITHHOLD
named_holds = [
    "evagrius-sententiae-monachos", "didymus-fragmenta-romanos", "macarius-spiritual-homilies",
    "origen-ezekiel-fragments", "origen-philocalia", "origen-romans-catena", "origen-de-principiis",
    "origen-letters", "origen-song-homily-1", "cyril-adoration-10",
    "pseudo-cyprian-to-vigilius", "didymus-dialexis-montanistae",
]
kept_named, held_named = site.split_withheld(
    [{"slug": slug, "status": "available"} for slug in named_holds]
    + [{"slug": "origen-song-homily-2", "status": "available"},
       {"slug": "origen-letters-gregory-series", "status": "available"}]
)
assert [w["slug"] for w in kept_named] == ["origen-song-homily-2", "origen-letters-gregory-series"], kept_named
assert held_named == named_holds, held_named
evag = json.loads((site.BOOKS / "evagrius-sententiae-monachos/translations/esm_u01_open_english.json").read_text())
evag_text = "\n".join(evag[0]["english"])
assert "Insert the superscription" not in evag_text
assert evag[0]["english"][0] == "To the monks who live in monasteries or in communities."
assert evag[0]["english"][1].startswith("Heirs of God, listen to the words of God.")
didy = json.loads((site.BOOKS / "didymus-fragmenta-romanos/translations/dfr_u01_rem_english.json").read_text())
close = next(row for row in didy if row["section"] == "u01-rem-close")
close_text = "\n".join(close["english"])
assert "Keep the English" not in close_text and "Add to translator_notes" not in close_text
assert "and likewise the good lies beside those who will to do evil" in close_text
assert any("οὐ καλὸν παράκειται" in note for note in close["translator_notes"])

import tempfile
with tempfile.TemporaryDirectory() as receipt_tmp:
    receipt_root = Path(receipt_tmp)
    (receipt_root / "sample-book" / "reviews").mkdir(parents=True)
    (receipt_root / "sample-book" / "reviews" / "work_receipt.json").write_text("{}")
    (receipt_root / "clean-book").mkdir()
    receipt_works = [{"slug": "sample-book"}, {"slug": "clean-book"}, {"slug": "no-folder"}]
    assert site.stale_receipt_slugs(
        receipt_works, books_root=receipt_root, certified_fn=lambda _n: False, pass_ab_fn=lambda _f: True,
    ) == ["sample-book"]
    assert site.stale_receipt_slugs(
        receipt_works, books_root=receipt_root, certified_fn=lambda _n: True, pass_ab_fn=lambda _f: False,
    ) == ["sample-book"]
    assert site.stale_receipt_slugs(
        receipt_works, books_root=receipt_root, certified_fn=lambda _n: True, pass_ab_fn=lambda _f: True,
    ) == []
    saved_work_book = site.work_book
    site.work_book = lambda slug: "sample-book" if slug == "alias" else saved_work_book(slug)
    try:
        assert site.stale_receipt_slugs(
            [{"slug": "alias"}], books_root=receipt_root,
            certified_fn=lambda _n: False, pass_ab_fn=lambda _f: True,
        ) == ["alias"]
    finally:
        site.work_book = saved_work_book

live_receipt = next(site.BOOKS.glob("*/reviews/work_receipt.json"))
live_book = live_receipt.parent.parent.name
sys.path.insert(0, str(site.BOOKS.parent / "scripts"))
sys.path.insert(0, str(site.BOOKS.parent))
import work_pipeline
from pipeline.check_pass_ab import check_translation_files
live_certified = work_pipeline.certified(live_book)
live_pairs = site._translation_pairs(site.BOOKS / live_book)
live_ab = bool(live_pairs) and all(
    src.is_file() and not check_translation_files(en, src) for en, src in live_pairs)
live_held = site.stale_receipt_slugs([{"slug": live_book}])
assert (live_book in live_held) == (not (live_certified and live_ab)), (live_book, live_certified, live_ab, live_held)

baron_title = "Philosophia theologiae ancillans (Exercitatio Prima Art. I-XII + Secunda Art. I-XV + Tertia Art. I-XXX)"
baron_sub = site.public_reader_latin_subtitle(baron_title, slug="baron-philosophia-theologiae-ancillans")
assert baron_sub == "Philosophia theologiae ancillans", baron_sub
assert site.public_reader_latin_subtitle(
    "Exercitatio Prima Art. I-XII + Secunda Art. I",
    slug="baron-philosophia-theologiae-ancillans",
) == ""
assert site.public_reader_latin_subtitle(
    "De oratione (Cap. I–XIV)",
    slug="baron-philosophia-theologiae-ancillans",
) == "De oratione"
baron_meta = json.loads((site.BOOKS / "baron-philosophia-theologiae-ancillans/translations/ente_art1_2_meta.json").read_text())
baron_blurb = site.public_blurb(baron_meta["blurb"])
assert "not in this volume" not in baron_blurb.lower() and "later exercise" not in baron_blurb.lower(), baron_blurb
assert "faith, science, and opinion" in baron_blurb
baron_method = site.public_note(site.public_method(baron_meta["text_history"]["method"]))
assert "remain" not in baron_method.lower() and "faith, science, and opinion" in baron_method, baron_method

placeus_meta = json.loads((site.BOOKS / "placeus-de-imputatione/translations/cap1_tip_meta.json").read_text())
placeus_blurb = site.public_blurb(placeus_meta["blurb"])
placeus_method = site.public_note(site.public_method(placeus_meta["text_history"]["method"]))
placeus_about = site.about_edition_text(placeus_meta["edition"])
for label, text in (("blurb", placeus_blurb), ("method", placeus_method), ("edition", placeus_about)):
    low = text.lower()
    assert "honest partial" not in low and "densify" not in low and "english follows" not in low, (label, text)
    assert "man. post" not in low, (label, text)
assert "from the Latin" in placeus_blurb and "chapters 1 to 12 and 14" in placeus_blurb, placeus_blurb  # no chapter 13 in the files
assert "1661 Saumur" in placeus_method and "chapters 1 to 12 and 14" in placeus_method, placeus_method
assert site.mast_edition_label(placeus_meta["edition"]) == "Saumur 1661"
assert site.public_blurb("Capita I–XIV from the Latin. Honest partial; more to come.") == ""
assert site.public_note("English follows the Latin partial through Man. Post. Caput IX.") == ""
for n in range(1, 18):
    adore = site.public_reader_latin_subtitle(
        f"On Adoration and Worship in Spirit and Truth, Book {n}",
        slug=f"cyril-adoration-{n}",
    )
    assert adore == "Περὶ προσκυνήσεως", (n, adore)
assert site.public_reader_latin_subtitle(
    "Syntagma sacrae theologiae (Liber I Cap. 10 densify complete)",
    slug="crocius-syntagma",
) == "Syntagma sacrae theologiae"
strim_meta = json.loads((site.BOOKS / "strimesius-in-controversias-evangelicorum/translations/prefatio_si_tip_meta.json").read_text())
strim_blurb = site.public_blurb(strim_meta["blurb"])
assert "honest partial" not in strim_blurb.lower() and "1708" in strim_blurb, strim_blurb
assert site.public_reader_latin_subtitle(strim_meta["title"], slug=strim_meta["slug"]) == "Ingenua in Controversias Evangelicorum"
assert "Prefatio" not in site.public_reader_title(strim_meta["title"], slug=strim_meta["slug"])
job_edition = site.imprint_with_known_volume("PG; Commentarii in Job (Khazarzar)", "didymus-commentarii-job")
assert "PG 39" in job_edition, job_edition
assert site.mast_edition_label(job_edition) == "PG 39", site.mast_edition_label(job_edition)
assert site.mast_edition_label("PG;") == ""
assert site.mast_edition_label("Migne PG 68") == "PG 68"
assert site.display_author("Paulus Silentarius") == "Paul the Silentiary"
assert 'author: "Paul the Silentiary"' in (site.BOOKS / "paulus-silentarius-ambonis/book.yml").read_text()
assert 'author: "Paul the Silentiary"' in (site.BOOKS / "paulus-silentarius-sophia/book.yml").read_text()
chrono = site.person_page_meta("chronicon-paschale", "Chronicon Paschale", works=1, passages=0)
assert chrono[2][0]["mainEntity"]["@type"] == "CreativeWork", chrono[2]
origen_meta = site.person_page_meta("origen", "Origen", works=1, passages=0)
assert origen_meta[2][0]["mainEntity"]["@type"] == "Person"
didache_meta = site.person_page_meta("didache", "Didache", works=1, passages=0)
assert didache_meta[2][0]["mainEntity"]["@type"] == "CreativeWork", didache_meta[2]
perpetua_meta = site.person_page_meta(
    "passion-of-perpetua-and-felicity", "Passion of Perpetua and Felicity", works=1, passages=0)
assert perpetua_meta[2][0]["mainEntity"]["@type"] == "CreativeWork"
assert site.author_schema_type(None, "The Didache") == "CreativeWork"
assert site.author_schema_type("origen", "Origen") == "Person"
assert site.public_reader_title("Letter to Rome (Fragments)", slug="julian-letter-to-rome") == "Fragments of the Letter to Rome"
assert site.public_reader_title(
    "To Turbantius — fragments in Against Julian", slug="julian-turbantius-fragments") == "Fragments to Turbantius"
assert site.public_reader_title("To Florus", slug="julian-to-florus") == "To Florus"
_printed, _ = site.mast_meta_line(
    {"author": "Julian of Eclanum", "author_slug": "julian-of-eclanum", "period": "1700"}, "")
assert "printed 1700 AD" in _printed and "written" not in _printed, _printed
_written, _ = site.mast_meta_line(
    {"author": "Julian of Eclanum", "author_slug": "julian-of-eclanum", "period": "c. 419–430"},
    "Quoted by Augustine")
assert "written c. 419–430 AD" in _written, _written
assert site.display_author("Theodorus (PG 86a)") == "Theodorus, not yet identified"
assert site.author_dates_display("Theodorus (PG 86a)", "theodorus-pg86a") == ""
assert site.confidence_text(site.CONFIDENCE_NOTE, True).startswith(
    "This work has passed this project's source check. ")
assert "independently certified" in site.confidence_text(site.CONFIDENCE_NOTE, True)
assert site.confidence_text(site.CONFIDENCE_NOTE, False).startswith(
    "This work has not yet been re-checked against its source. ")
assert site.section_orientation_html({"orientation": "The preacher opens."}).startswith(
    '<p class="reader-note">')
assert site.section_orientation_html({}) == ""
assert site._origen_rows(
    [{"section": "1", "english": ["Hello."], "orientation": "A note."}], {})[0]["orientation"] == "A note."
_mapped_books = set(site.WORK_BOOK_INTRO)
_intro_slug = ""
for _intro_path in site.BOOKS.glob("*/intro.md"):
    _name = _intro_path.parent.name
    if _name in _mapped_books or any(_name.startswith(pref) for pref, _cand in site.WORK_BOOK_PREFIXES):
        continue
    _intro_slug = _name
    break
assert _intro_slug and site.work_book(_intro_slug) == _intro_slug, _intro_slug
_grace_grams = site.search_trigrams([{"title": "On Grace", "author": "Gregory", "text": "grace upon grace"}])
_other_grams = site.search_trigrams([{"title": "Note", "author": "Cyril", "text": "xyzzy plugh"}])
assert site.search_grams_cover(_grace_grams, "gra") and not site.search_grams_cover(_grace_grams, "xyz")
assert not site.search_grams_cover(_other_grams, "gra") and site.search_grams_cover(_other_grams, "xyz")
assert site.search_grams_cover("", "gra")
with tempfile.TemporaryDirectory() as _search_tmp:
    _search_root = Path(_search_tmp)
    _search_docs = [
        {"kind": "work", "id": "a", "title": "On Grace", "author": "Gregory", "text": "grace upon grace", "href": "/works/a/"},
        {"kind": "work", "id": "b", "title": "Letters", "author": "Basil", "text": "the gravity of sin", "href": "/works/b/"},
    ]
    assert site.write_search_shards(_search_root, _search_docs) >= 1
    assert not (_search_root / "search-index.json").exists()
    assert {r["id"] for r in site.load_search_docs(_search_root)} == {"a", "b"}
    _search_man = json.loads((_search_root / "search" / "manifest.json").read_text())
    assert all(s.get("grams") for s in _search_man["shards"])

if "--publication-only" in sys.argv:
    print("publication gate: offline attack regressions passed")
    raise SystemExit(0)

excerpts = site.load_topic_excerpts()
assert len({x["id"] for x in excerpts}) == len(excerpts)
paenitentia = {x["id"]: x for x in excerpts if x["id"].startswith("tertullian_paenitentia_7")}
assert paenitentia["tertullian_paenitentia_7"]["topic"] == "faith-and-obedience"
assert paenitentia["tertullian_paenitentia_7--discipline-penance"]["topic"] == "discipline-penance"
assert (site.DIST / "404.html").exists()
collective = next(w for w in site.load_julian_works() if w["slug"] == "julian-collective-letter")
assert len({r["section"] for r in collective["sections"]}) == len(collective["sections"])
assert any(r["section"] == "4-2-2" for r in collective["sections"])
assert sum(r["section"].startswith("4-2-2-collective-") for r in collective["sections"]) == 8

assert site.year_from_period("c. 6th cent.") == 550
assert site.year_from_period("c. 340–395") == 367
assert site.year_from_period("fl. c. 50 BC") == -50
assert site.year_from_period("c. 130–c. 202") == 166
assert site.year_from_period("c. 130–c. 202", bound="end") == 202
assert site.format_bc_ad("c. 130–c. 202") == "c. 130–c. 202 AD"
assert site.format_bc_ad("fl. c. 50 BCE") == "fl. c. 50 BC"
assert site.format_bc_ad("4th century CE") == "4th century AD"
assert site.format_bc_ad("1708 (Frankfurt)") == "1708 AD (Frankfurt)"
assert site.author_sort_year("Clement of Rome", slug="clement-of-rome") == 96
assert site.author_sort_year("Hermas", slug="hermas") == 140
assert site.author_sort_year("Justin Martyr", slug="justin-martyr") == 165
assert site.author_sort_year("Irenaeus of Lyons", slug="irenaeus") == 202
assert site.author_sort_year("Julius Africanus", slug="julius-africanus") == 240
assert (
    site.author_sort_year("Hermas", slug="hermas")
    < site.author_sort_year("Justin Martyr", slug="justin-martyr")
    < site.author_sort_year("Irenaeus of Lyons", slug="irenaeus")
    < site.author_sort_year("Julius Africanus", slug="julius-africanus")
)
assert site.work_era({"author": "Unlisted writer", "period": "c. 6th cent."}) == "Post-Nicene"
# A century period files under its middle year, never "Unknown" (no chip reaches it).
assert site.work_era({"author": "Unlisted writer", "period": "c. 5th cent."}) == "Nicene"
assert site.work_era({"author": "Polycarp of Smyrna", "author_slug": "polycarp-of-smyrna", "period": "c. 155"}) == "Apostolic"
assert site.work_era({"author": "Unlisted writer", "period": "c. 880"}) == "Byzantine"
assert site.work_era({"author": "Unlisted writer", "period": "1636"}) == "Reformation"
assert site.era_band(120) == "Apostolic"  # Explore points keep the old year bands
assert site.year_from_period("date uncertain") is None
work = site._pack_work(slug="unsubstantiated", title="A <work>", author="A & B",
    author_slug="a-b", period="c. 6th cent.", status="in_progress", edition="Test",
    sections=[{"section": "1", "english": ["A real sentence."]}],
    first_english=True, first_english_note="No previous English translation.",
    blurb="Original English Translation — ANF does not cover this work.")
assert not work["first_english"] and not work["first_english_note"]
assert "Original English Translation" not in work["blurb"]
card = site.work_card_html(work, catalog=True)
assert "Translation in progress" in card and "1 section ·" in card
assert "A &lt;work&gt;" in card and "A &amp; B" in card
assert "Available" not in card and "Unknown" not in card
assert "Original English Translation" not in card
assert 'data-author-href="/authors/a-b/"' in card

class Catalogue(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.has_author_catalog = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "ul" and a.get("id") == "works-list" and "author-catalog" in (a.get("class") or ""):
            self.has_author_catalog = True
        if tag == "li" and ("data-author" in a) and ("author-entry" in (a.get("class") or "") or "data-works" in a):
            self.rows.append(a)

page = Catalogue()
works_html = (site.DIST / "works/index.html").read_text()
page.feed(works_html)
# The receipt that belongs to this dist (build_site writes it next to DIST);
# the shared outputs/ copy only for an old build that predates that.
_receipt_path = site.DIST.parent / f"{site.DIST.name}.catalogue-quality.json"
if not _receipt_path.exists():
    _receipt_path = site.ROOT / "outputs/catalogue-quality.json"
receipt = json.loads(_receipt_path.read_text())
assert page.has_author_catalog, "Works page missing author-catalog class"
assert "Book 1" not in works_html, "Works catalogue still shows Book 1 sprawl"
_ws = re.search(
    r"densify|\btip\b|\blocked\b|staging|Latin column|Greek OCR|_meta\b|private study"
    r"|starts PHYS|next PHYS|new OET|SERIES CLOSEOUT|folio|sigla|obelus|pinax",
    works_html, re.I)
_ws_caps = re.search(
    r"\bPHYS\b|\bOCR\b|\bCOMPLETE\b|\bCLOSEOUT\b|\bFINIS\b|\bTODO\b"
    r"|FOUND PHYS|NOT FOUND|Liber [IVX]+\b|Exercitatio|\bPG \d|\bANF \d"
    r"|Salmond|Crombie|Walford|Routh|Bidez|Vossius|Wither|Migne",
    works_html)
assert not _ws and not _ws_caps, "Works catalogue shows worksheet scaffolding"
assert len(page.rows) > 0, "No author-entry rows on Works"
work_total = sum(int(r.get("data-works") or "0") for r in page.rows)
assert work_total == receipt["published_works"], (work_total, receipt["published_works"])
assert receipt["published_works"] >= 57, receipt["published_works"]
assert "publication_review_failures" in receipt
failed_excerpts = {key.removeprefix("excerpt:") for key in receipt["publication_review_failures"] if key.startswith("excerpt:")}
assert receipt["published_excerpts"] == len([x for x in excerpts if x["id"] not in failed_excerpts])
assert len({r["data-author"] for r in page.rows}) == len(page.rows)
assert all(r.get("data-oet") in {"0", "1"} for r in page.rows)
held = {r["slug"] for r in receipt["held_works"]}
assert "agathias-historiae" in held
index = site.load_search_docs(site.DIST / "data")
for key in receipt["publication_review_failures"]:
    if key.startswith("work:"):
        assert key.split(":", 2)[1] in held, "publication failure was not held"
    else:
        excerpt_id = key.removeprefix("excerpt:")
        assert not any(row.get("id") == excerpt_id for row in index), "failed excerpt remained searchable"
        assert not (site.DIST / "e" / excerpt_id / "index.html").exists(), "failed excerpt remained public"
assert not any(row.get("href", "").split("/")[2:3] == [slug]
               for row in index for slug in held)
assert not any((site.DIST / "works" / slug / "index.html").exists() for slug in held)
for tail in receipt.get("held_tail_sections", []):
    slug = tail["slug"]
    assert slug not in held, "tail-held work was fully held"
    assert (site.DIST / "works" / slug / "index.html").exists(), "tail-held work missing"
    for section in tail["held_sections"]:
        assert not any(row.get("href", "").split("/")[2:4] == [slug, str(section)]
                       for row in index), f"held tail section remained searchable: {slug} {section}"
        assert not (site.DIST / "works" / slug / str(section) / "index.html").exists(), \
            f"held tail section remained public: {slug} {section}"
# Bible references in reader English use the standard form ("Zechariah 3:8-9"),
# never an old edition's Latin abbreviation with a Roman chapter ("Zach. III, 8-9").
_ROMAN_REF = re.compile(
    r"(?<![A-Za-z])(?:Gen|Ex|Exod|Lev|Num|Deut|Jos|Judic|Reg|Par|Esd|Ps|Prov|Eccl|Cant|Is|Isa|Jer|Ezech|Dan"
    r"|Os|Joel|Am|Mich|Hab|Soph|Agg|Zach|Mal|Matth|Marc|Luc|Joan|Act|Rom|Cor|Gal|Eph|Phil|Col|Thess"
    r"|Tim|Tit|Hebr|Jac|Petr|Jud|Apoc)\.\s+[IVXLC]{1,7},\s*\d")
_body = re.compile(r'<div class="body">(.*?)</div>', re.S)
_roman_hits = []
for _page in sorted((site.DIST / "works").glob("*/*/index.html")):
    _m = _body.search(_page.read_text(encoding="utf-8"))
    if _m and _ROMAN_REF.search(re.sub(r"<[^>]+>", "", _m.group(1))):
        _roman_hits.append(_page.parent.relative_to(site.DIST).as_posix())
assert not _roman_hits, "Roman-numeral Bible references in reader text: %s" % _roman_hits[:5]
# Worksheet notes ("lock" is the translators' word for a damaged passage) never reach readers.
_LOCK_NOTE = re.compile(r"\[[^\]]{0,40}\block\b[^\]]{0,60}\]|\block (?:marks|unrestored)\b", re.I)
_lock_hits = [p.parent.name for p in sorted((site.DIST / "works").glob("*/index.html"))
              if _LOCK_NOTE.search(re.sub(r"<[^>]+>", "", p.read_text(encoding="utf-8")))]
assert not _lock_hits, "Worksheet lock notes in reader text: %s" % _lock_hits[:5]
# Every writer has a date and an era chip, except the named undated ones
# (no chip can reach a data-era="Unknown" row; 2026-10-07 audit).
_unknown_era = {re.search(r"/authors/([^/]+)/", r.get("data-author-href") or "").group(1)
                for r in page.rows if r.get("data-era") == "Unknown" and r.get("data-author-href")}
assert _unknown_era <= set(site.UNDATED_AUTHORS), "works rows with no era chip: %s" % sorted(_unknown_era)
_undated_path = site.DIST.parent / f"{site.DIST.name}.authors-without-dates.json"
if _undated_path.exists():
    _undated = set(json.loads(_undated_path.read_text()))
    assert _undated <= set(site.UNDATED_AUTHORS), "writers without dates: %s" % sorted(_undated - set(site.UNDATED_AUTHORS))
print(json.dumps({"status": "passed", "authors": len(page.rows), "works": work_total, "held": len(held)}))

assert site.display_section("4-2-2-collective-23") == "4.2.2"
assert site.display_section("1.27") == "1.27"
class VisibleText(HTMLParser):
    """Text a reader sees: skips script/style (JSON-LD carries real URLs)."""
    def __init__(self):
        super().__init__()
        self.text = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)
visible = VisibleText()
visible.feed((site.DIST / "works/julian-collective-letter/index.html").read_text())
assert "-collective-" not in " ".join(visible.text)

# A stale human review packet does not stop the ship. The page is the current
# reading. Reader corrections are on /contribute/.

assert site._section_sort_key("2-5-9") < site._section_sort_key("2-5-10")
assert site._section_sort_key("4-2-2-collective-23") == site._section_sort_key("4-2-2")
source_collective = json.loads((site.JULIAN_BOOK / "translations/collective_letter_english.json").read_text())
assert [row["english"] for row in collective["sections"]] == [row["english"] for row in source_collective]

for slug, filenames in {
    "julian-turbantius-fragments": [f"contra_julianum_{book}_english.json" for book in range(1, 7)],
    "julian-marriage-extracts": ["marriage2_english.json"],
    "julian-letter-to-rome": ["letter_to_rome_english.json"],
}.items():
    expected_rows = [row for filename in filenames for row in json.loads(
        (site.JULIAN_BOOK / "translations" / filename).read_text())]
    loaded = next(w for w in site.load_julian_works() if w["slug"] == slug)
    assert [row["english"] for row in loaded["sections"]] == [
        site.eng_list(row.get("english")) for row in expected_rows], slug

# English-first titles: no published work page may lead its H1 with Latin.
# Latin lives only in the secondary subtitle line. Held works are unaffected
# until the day they publish, when this gate forces the English title then.
LATIN_H1 = re.compile(
    r"^(De|In(?!\s+(?:Praise|the|Defen[cs]e|Honou?r|Memory|Answer|Reply|Response)\b)|Contra|Adversus|Pro|Ex|Fragmenta|Fragmentum|Commentarii|"
    r"Homilia|Homiliae|Epistula|Epistulae|Oratio|Orationes|Sermo|Tractatus|"
    r"Liber|Tomus|Capitula|Scholia(?!\s+on\b)|Catena|Refutatio|Demonstratio|"
    r"Testamentum|Testimonia|"
    r"Bibliotheca|Panarion|Ancoratus|Anacephalaeosis|Chronicon|Chronographia|"
    r"Historiae|Vita|Passio|Martyrium|Encomium|Laudatio|Apologia)\b")
for _page in sorted((site.DIST / "works").glob("*/index.html")):
    _h1 = re.search(r"<h1>(.*?)</h1>", _page.read_text(), re.S)
    assert _h1, "work page without H1: %s" % _page.parent.name
    _title = re.sub(r"<[^>]+>", "", _h1.group(1)).strip()
    assert not LATIN_H1.match(_title), \
        "Latin-primary H1 on /works/%s/: %s" % (_page.parent.name, _title)

# Made-up teaser lines (2026-10-06 audit). A loader once filled missing blurbs
# with "<Author> Greek fragments. SERIES CLOSEOUT.", which put "Tertullian Greek
# fragments." on complete Latin works. Fail only on that exact stub for the
# page's own writer, so an honest "Surviving Greek fragments." still ships.
import html as _html
_DESC = re.compile(r'<meta name="description" content="([^"]*)"')
_LD_AUTHOR = re.compile(r'"author": \{"@type": "(?:Person|CreativeWork)", "name": "([^"]+)"')
_stub_hits = []
for _page in sorted((site.DIST / "works").glob("*/index.html")):
    _s = _page.read_text(encoding="utf-8")
    _m = _DESC.search(_s)
    _d = _html.unescape(_m.group(1)) if _m else ""
    _a = _LD_AUTHOR.search(_s)
    _author = _html.unescape(_a.group(1)) if _a else ""
    if "SERIES CLOSEOUT" in _d or (_author and _d in (f"{_author} Greek fragments.", f"{_author} Latin fragments.")):
        _stub_hits.append(_page.parent.name)
assert not _stub_hits, "Placeholder '<Author> Greek fragments.' blurb on: %s" % _stub_hits[:8]
assert site._CATALOGUE_STUB.search("Tertullian Greek fragments.")
assert not site._CATALOGUE_STUB.search("Surviving Greek fragments.")

# Warn (not fail) on certified books with no blurb: the page then uses the
# intro.md or work-brief line, or a neutral sentence. A real blurb is better.
_no_blurb = []
for _folder in sorted(site._CERTIFIED):
    _metas = [json.loads(_p.read_text(encoding="utf-8")) for _p in (_folder / "translations").glob("*_meta.json")]
    if _metas and not any((_m.get("work_blurb") or _m.get("blurb") or "").strip() for _m in _metas):
        _no_blurb.append(_folder.name)
if _no_blurb:
    print(json.dumps({"warn": "certified books with no meta blurb", "books": _no_blurb}))

# Unit checks for the display helpers behind the gates below (2026-10-06).
_w = {"slug": "x", "title": "T"}
assert site.display_head({"section": "1", "head": "Ask, seek, knock — GREGORY CLOSEOUT SERIES CLOSEOUT"}, _w) == "Ask, seek, knock"
assert site.display_head({"section": "1", "head": "Expositio in Proverbia Unit 1 opening"}, _w) == ""
assert site.display_head({"section": "1", "head": "Unit 7 rem early — armor as Christ"}, _w) == "armor as Christ"
assert site.display_head({"section": "1", "head": "John catena rem CLOSEOUT: passion"}, _w) == "John catena: passion"
assert "PLAC" not in site.display_head({"section": "1", "head": "Man. Post. Cap. IX: PLAC — Apostle never said"},
                                       {"slug": "placeus-de-imputatione", "title": "T"})
assert "Christ</a>. Yet" in site.render_reader_html("fullness of [[Christ >> Bible:Ephesians 4:13]]. Yet every judgment")
assert site.clean_reader_notation("he said, [the text breaks off]") == "he said. The text breaks off."
assert site.section_ordinals(["gregory-1", "gregory-close"]) == {"gregory-1": "1", "gregory-close": "2"}
assert site.section_ordinals(["praef", "1", "epilogus_alius"]) == {"praef": "Preface", "epilogus_alius": "Second epilogue"}
assert "Scapula" in site._fallback_blurb(site.BOOKS / "tertullian-to-scapula", "Tertullian: To Scapula", "Tertullian")

# Build-room labels in headings and search titles, words glued to a Bible
# link ("Christ</a>Yet"), and raw section ids: none may reach readers.
_LABEL = re.compile(r"CLOSEOUT|\bUnit \d+\b|\brem (?:early|mid|close)\b")
_GLUE = re.compile(r'class="bible-ref"[^>]*>[^<]*</a>[A-Za-z]')
_RAW_ID = re.compile(r"§(?:[a-z]+-)+(?:\d+|close|mid|open)\b|§(?:praef|proem|epilogus\w*)\b")
_label_hits, _glue_hits, _id_hits = [], [], []
for _page in sorted((site.DIST / "works").glob("*/*/index.html")) + sorted((site.DIST / "works").glob("*/index.html")):
    _s = _page.read_text(encoding="utf-8")
    _rel = _page.parent.relative_to(site.DIST).as_posix()
    if _GLUE.search(_s):
        _glue_hits.append(_rel)
    _heads = re.findall(r"<h[12][^>]*>(.*?)</h[12]>", _s, re.S) + re.findall(r"<title>(.*?)</title>", _s, re.S)
    if any(_LABEL.search(re.sub(r"<[^>]+>", "", _h)) for _h in _heads):
        _label_hits.append(_rel)
    if _RAW_ID.search(re.sub(r"<[^>]+>", " ", _s.split("<main", 1)[-1])):
        _id_hits.append(_rel)
_search_label_hits = [row.get("title", "") for row in index if _LABEL.search(row.get("title", ""))]
assert not _label_hits, "Build-room labels in headings: %s" % _label_hits[:5]
assert not _search_label_hits, "Build-room labels in search titles: %s" % _search_label_hits[:5]
assert not _glue_hits, "Words glued to a Bible link: %s" % _glue_hits[:5]
assert not _id_hits, "Raw section ids shown to readers: %s" % _id_hits[:5]
assert not [t for t in (row.get("title", "") for row in index) if t.endswith(":")], "search title ends in ':'"

# Part-only works say so on their page (2026-10-06: the one-paragraph Panarion
# looked like the whole book). Any book meta with "scope" must show it.
_scoped = {}
for _p in site.BOOKS.glob("*/translations/*_meta.json"):
    try:
        _m = json.loads(_p.read_text(encoding="utf-8"))
    except ValueError:
        continue
    if isinstance(_m, dict) and _m.get("scope") and _m.get("slug"):
        _scoped[_m["slug"]] = _m["scope"]
_unshown = [slug for slug in _scoped if (site.DIST / "works" / slug / "index.html").exists()
            and "Part only:" not in (site.DIST / "works" / slug / "index.html").read_text(encoding="utf-8")]
assert not _unshown, "scope set but not shown: %s" % _unshown[:5]
# A book that calls itself complete must have every source section in English.
_sources = json.loads((site.DIST / "data/work-sources.json").read_text())
assert not _sources["unresolved"], "published works with no book folder: %s" % _sources["unresolved"][:5]
_short = []
for _slug, _src in _sources["works"].items():
    _yml = site.BOOKS / _src["book"] / "book.yml"
    _scope = re.search(r'^scope:\s*"?(.*?)"?\s*$', _yml.read_text(encoding="utf-8"), re.M) if _yml.exists() else None
    if _slug in _scoped or not _scope or not _scope.group(1).lower().startswith("complete"):
        continue
    _en = _src_n = 0
    for _stem in _src["stems"]:
        _tr = site.BOOKS / _src["book"] / "translations"
        _e, _so = _tr / f"{_stem}.json", _tr / f"{_stem[:-len('_english')]}_source.json"
        if _e.exists() and _so.exists():
            _en += len([r for r in json.loads(_e.read_text(encoding="utf-8")) if not isinstance(r, dict) or r.get("english")])
            _src_n += len(site._source_rows(json.loads(_so.read_text(encoding="utf-8"))))
    if _src_n and _en < _src_n:
        _short.append(f"{_slug} {_en}/{_src_n}")
assert not _short, "book.yml says complete but sections are missing: %s" % _short[:5]
print(json.dumps({"status": "passed", "check": "reader text hygiene", "part_only_works": len(_scoped)}))

# Works reader polish (2026-10-06 audit, P12): slim mast, English titles in
# every public line, no workroom text in the reading column.
assert site.mast_edition_label("De imputatione primi peccati Adami (Salmurii: Apud Ioannem Lesnerium, 1661)") == "Saumur 1661"
assert site.mast_edition_label("Klostermann, Origenes Werke III (GCS 6, 1901)") == "Klostermann (1901)"
assert site.mast_edition_label("PG 10; Cesti fragmenta extract of books 7, 2, 3, 4, 8, 9, and 13)") == "PG 10"
assert site.mast_edition_label("First1KGreek TEI — John/Luke catena") == ""
assert site.clean_reader_notation("he said [text is garbled/gapped] and") == "he said [The text is damaged here.] and"
assert site.clean_reader_notation("[Here T has a gap of about 100 letters.]") == "[The text is damaged here.]"
assert site.shown_source(["κατὰ τὸνἸησοῦν 77.288 καὶ"]) == ["κατὰ τὸν Ἰησοῦν ‹77.288› καὶ"]
# Latin text that quotes a Greek word keeps every line; catena loci stay.
assert site.shown_source(["Hinc ansam arripit.\n\nSed nescio quid τὸ ἀντίτυπον."], "l") == [
    "Hinc ansam arripit.\n\nSed nescio quid τὸ ἀντίτυπον."]
assert site.shown_source(["Hinc ansam arripit.\n\nSed nescio quid τὸ ἀντίτυπον."])[0].startswith("Hinc")
assert site.shown_source(["Fragmenta in epistulam ad Philemonem (in catenis)\nPhm\nτοῦ Παύλου"], "g") == ["Phm\nτοῦ Παύλου"]
assert site.clean_reader_notation("[Here T is illegible; the editors conjecture mockery of prayers.]") == (
    "[The text is damaged here; the editors conjecture mockery of prayers.]")
assert site.shown_source(["absit \\'a seruo"]) == ["absit 'a seruo"]
assert site.public_head("Liber IV recapitulation") == "Book 4 recapitulation"
assert site.public_head("Scripture locked and sealed (Philoc. 2)") == "Scripture locked and sealed"
assert site.work_teaser_html({"blurb": ""}) == "", "filler teaser line came back"
_MAST = re.compile(r'<header class="reader-mast"[^>]*>.*?<p class="meta">(.*?)</p>', re.S)
_SUB = re.compile(r'<h1>(.*?)</h1>\s*<p class="latin-title">(.*?)</p>', re.S)
_TOC = re.compile(r'<span class="toc-label">(.*?)</span></a>', re.S)
_RULE1 = re.compile(r"\b(?:Anaphora|Apophthegmata|Hexaemeron|Praktikos|Cesti|Scholia|Enarration|Octateuch"
                    r"|Recension|Philocalia|Philoc\.|Liber\s+[IVX]+|Homilia\s+[IVX]+|Sermo\s+[IVX]+)\b")
_H1_PAREN = re.compile(r"\((?:Greek|Latin|\d|Vat\.)")
_IMPRINT = re.compile(r"typography of|In Leipzig|\bYear 18\d\d\b|Apud |Salmurii|Sancti patris")
_WORKROOM = re.compile(r"This is a listening version|placeholders\]|\[text (?:is )?(?:garbled|corrupt)|\[Here T\b|Densify")
_plain = lambda h: _html.unescape(re.sub(r"<[^>]+>", "", h)).strip()
_mast_long, _mast_latin, _echo, _toc_hits, _h1_hits, _imprint_hits, _workroom_hits = [], [], [], [], [], [], []
_mast_form, _latin_english, _scope_hidden = [], [], []
_LATIN_ENGLISH = re.compile(r"\((?:the|a|an|on|of)\b|\b(?:the|and|of|Homily|Sermon|Letter|Fragments)\b")
_SCOPE_SENT = re.compile(r"This (?:volume|book) (?:holds|gathers|contains|opens)\b")
for _page in sorted((site.DIST / "works").glob("*/index.html")) + sorted((site.DIST / "works").glob("*/book-*/index.html")):
    _s = _page.read_text(encoding="utf-8")
    _rel = _page.parent.relative_to(site.DIST).as_posix()
    _m = _MAST.search(_s)
    if _m:
        _meta = _plain(_m.group(1))
        if len(_meta) > 90:
            _mast_long.append(f"{_rel} ({len(_meta)})")
        if _IMPRINT.search(_meta):
            _mast_latin.append(_rel)
        if ") (" in _meta or "?" in _meta or "cent." in _meta:
            _mast_form.append(f"{_rel}: {_meta}")
    _lt = re.search(r'<p class="latin-title">(.*?)</p>', _s, re.S)
    if _lt and _LATIN_ENGLISH.search(_plain(_lt.group(1))):
        _latin_english.append(f"{_rel}: {_plain(_lt.group(1))}")
    # A part-only work says so above the text: Part only in the mast, or the
    # intro's scope sentence as the lede.
    _top = _s.split('<div class="reader-layout">', 1)[0]
    if "/book-" not in _rel and _SCOPE_SENT.search(_html.unescape(_s)) and "Part only" not in _plain(_top) \
            and not _SCOPE_SENT.search(_plain(_top)):
        _scope_hidden.append(_rel)
    _sm = _SUB.search(_s)
    if _sm and site._same_title_words(_plain(_sm.group(2)), _plain(_sm.group(1))):
        _echo.append(_rel)
    _h1 = re.search(r"<h1>(.*?)</h1>", _s, re.S)
    if _h1 and (_H1_PAREN.search(_plain(_h1.group(1))) or _RULE1.search(_plain(_h1.group(1)))):
        _h1_hits.append(_rel)
    if any(_RULE1.search(_plain(t)) for t in _TOC.findall(_s)):
        _toc_hits.append(_rel)
    _body = _s.split('<div class="reader-main">', 1)[-1] if '<div class="reader-main">' in _s else ""
    _body = re.sub(r"<details.*?</details>", "", _body, flags=re.S)
    if _IMPRINT.search(_plain(_body)):
        _imprint_hits.append(_rel)
    if _WORKROOM.search(_plain(_body)) or 'class="range">§§' in _s:
        _workroom_hits.append(_rel)
_search_rule1 = [row.get("title", "") for row in index if _RULE1.search(row.get("title", ""))]
assert not _mast_long, "mast meta over 90 characters: %s" % _mast_long[:5]
assert not _mast_latin, "Latin imprint words in the mast: %s" % _mast_latin[:5]
assert not _echo, "subtitle repeats the English H1: %s" % _echo[:5]
assert not _h1_hits, "H1 with (Greek)/(Latin)/shelfmark or a rule-1 word: %s" % _h1_hits[:5]
assert not _toc_hits, "rule-1 word in Contents labels: %s" % _toc_hits[:5]
assert not _search_rule1, "rule-1 word in search titles: %s" % _search_rule1[:5]
assert not _imprint_hits, "printer's imprint in reader text: %s" % _imprint_hits[:5]
assert not _workroom_hits, "workroom text in reader text: %s" % _workroom_hits[:5]
assert not _mast_form, "mast with ') (', '?' or 'cent.': %s" % _mast_form[:5]
assert not _latin_english, "English in the Latin subtitle slot: %s" % _latin_english[:5]
assert not _scope_hidden, "part-only work hides its scope in About: %s" % _scope_hidden[:5]
_placeus = site.DIST / "data" / "src" / "placeus-de-imputatione.json"
if _placeus.exists():
    assert "Hinc ansam arripit" in " ".join(json.loads(_placeus.read_text(encoding="utf-8"))["28"].get("l") or []), \
        "Placeus §28 Latin lost its opening paragraph"
print(json.dumps({"status": "passed", "check": "reader polish (P12)"}))
