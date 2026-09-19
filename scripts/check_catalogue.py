"""Focused catalogue regression checks; run with the translations Python."""
import json
from html.parser import HTMLParser
from pathlib import Path
import build_site as site
from catalogue_quality import self_check, check_publication, publication_inventory, publication_digest, work_scope

self_check()

# New/changed content cannot inherit the legacy screen or self-attest a review.
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
    assert check_publication([], [row], root, corpus)[1] == [row]
    changed = {**row, "english": ["A different meaning."]}
    assert not check_publication([], [changed], root, corpus)[1]
    manifest["reviews"]["excerpt:fixture"] = {"packet": "../outside.json", "receipt": "none"}
    (root / "data/publication-review.json").write_text(json.dumps(manifest))
    assert check_publication([], [changed], root, corpus)[3]
    scaffold = {**row, "english": ["Lemma-led open — source"]}
    manifest["provisional_legacy"]["excerpt:fixture"] = publication_digest(
        publication_inventory([], [scaffold])["excerpt:fixture"])
    (root / "data/publication-review.json").write_text(json.dumps(manifest))
    assert not check_publication([], [scaffold], root, corpus)[1]

# A reviewed packet cannot be transplanted to another author/work, and one
# packet is validated once even when it authorizes several selected passages.
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
        "notes": "The named print contains both complete sentences; negation and agency match.",
        "uncertainties": [], "covered_source_paragraphs": [1]}
    receipt = {"packet_id": packet["packet_id"], "reviewer": "offline fixture", "verdict": "pass",
               "reviews": [{**semantic, "section": row["section"]} for row in rows], "scope_review": semantic}
    (corpus / "packet.json").write_text(json.dumps(packet))
    (corpus / "receipt.json").write_text(json.dumps(receipt))
    pair = {"packet": "packet.json", "receipt": "receipt.json"}
    manifest = {"schema": "fathers-publication-v1", "provisional_legacy": {}, "reviews": {
        key: {**pair, "section": value["row"]["section"], "payload_sha256": publication_digest(value)}
        for key, value in publication_inventory([work], []).items()}, "scope_reviews": {"fixture": pair}}
    manifest_path = root / "data/publication-review.json"
    manifest_path.write_text(json.dumps(manifest))
    with patch("pipeline.verify_translation_qa.validate_audit_receipt", wraps=validate_audit_receipt) as validate:
        kept, _, _, errors = check_publication([work], [], root, corpus)
        assert kept == [work] and not errors, errors
        assert validate.call_count == 1, "same packet rehashed for every passage"
    transplanted = {**work, "author": "Author B", "title": "Work B"}
    for key, value in publication_inventory([transplanted], []).items():
        manifest["reviews"][key]["payload_sha256"] = publication_digest(value)
    manifest["provisional_work_scopes"] = {"fixture": publication_digest(work_scope(transplanted))}
    manifest_path.write_text(json.dumps(manifest))
    assert not check_publication([transplanted], [], root, corpus)[0], "cross-work review transplant passed"
    manifest = {"schema": "fathers-publication-v1", "reviews": {},
                "provisional_work_scopes": {"fixture": publication_digest(work_scope(work))},
                "provisional_legacy": {key: publication_digest(value) for key, value in publication_inventory([work], []).items()}}
    manifest_path.write_text(json.dumps(manifest))
    assert check_publication([work], [], root, corpus)[0] == [work]
    for changed in ({**work, "sections": rows[:1]}, {**work, "sections": list(reversed(rows))},
                    {**work, "edition": "Another print"}, {**work, "blurb": "Complete works, critically certified"}):
        assert not check_publication([changed], [], root, corpus)[0], "scope/disclosure change inherited legacy approval"
    empty = {**work, "sections": []}
    from catalogue_quality import partition_catalogue
    assert not partition_catalogue([empty])[0], "zero-section work passed catalogue gate"
    assert not check_publication([empty], [], root, corpus)[0], "zero-section work passed publication gate"

import sys
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
assert site.work_era({"author": "Unlisted writer", "period": "c. 5th cent."}) == "Unknown"
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
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li" and "data-title" in a:
            self.rows.append(a)

page = Catalogue()
page.feed((site.DIST / "works/index.html").read_text())
receipt = json.loads((site.ROOT / "outputs/catalogue-quality.json").read_text())
assert len(page.rows) == receipt["published_works"]
assert "publication_review_failures" in receipt
failed_excerpts = {key.removeprefix("excerpt:") for key in receipt["publication_review_failures"] if key.startswith("excerpt:")}
assert receipt["published_excerpts"] == len([x for x in excerpts if x["id"] not in failed_excerpts])
assert len({r["data-title"] + r["data-author"] for r in page.rows}) == len(page.rows)
assert all(r["data-oet"] == "0" for r in page.rows)
held = {r["slug"] for r in receipt["held_works"]}
assert "agathias-historiae" in held
index = json.loads((site.DIST / "data/search-index.json").read_text())
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
print(json.dumps({"status": "passed", "works": len(page.rows), "held": len(held)}))

assert site.display_section("4-2-2-collective-23") == "4.2.2"
assert site.display_section("1.27") == "1.27"
class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
visible = VisibleText()
visible.feed((site.DIST / "works/julian-collective-letter/index.html").read_text())
assert "-collective-" not in " ".join(visible.text)

# Revalidate live source bindings at ship time too, even when dist is reused.
manifest = json.loads((site.ROOT / "data/publication-review.json").read_text())
current_pairs = set()
for key, review in manifest.get("reviews", {}).items():
    parts = key.split(":", 2)
    public_path = (site.DIST / "works" / parts[1] / "index.html"
                   if parts[0] == "work" else site.DIST / "e" / parts[1] / "index.html")
    if public_path.exists():
        current_pairs.add((review["packet"], review["receipt"]))
for slug, review in manifest.get("scope_reviews", {}).items():
    if (site.DIST / "works" / slug / "index.html").exists():
        current_pairs.add((review["packet"], review["receipt"]))
for packet_path, receipt_path in current_pairs:
    packet = json.loads((site.BOOKS.parent / packet_path).read_text())
    semantic_receipt = json.loads((site.BOOKS.parent / receipt_path).read_text())
    assert not validate_audit_receipt(packet, semantic_receipt), "Published source review became stale"

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
