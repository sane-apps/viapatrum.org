#!/usr/bin/env python3
"""The app's content digest must change when only catalog rows change.

The app skips a sync when catalog "content" is unchanged (Library.swift), so a
Listen flag, title or topic change with the same bodies has to move it.
Run: python3 scripts/app_export_test.py
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app_export

# Just enough of build_site for write(): plain text through, no Scripture refs.
FAKE_B = SimpleNamespace(
    BIBLE_ORDER=["Genesis", "John"],
    AUTHOR_BIOS={},
    display_author=lambda name: name,
    author_hub_slug=lambda name: name.lower().replace(" ", "-"),
    author_dates_display=lambda name, key: "",
    author_sort_year=lambda name, _x, key: 300,
    work_book=lambda slug: slug,
    section_ordinals=lambda sections: {},
    shown_section=lambda section, ordinals: str(section),
    public_head=lambda head: head,
    display_head=lambda s, w: str(s.get("head") or "").replace(" GAR 3 tip", ""),
    clean_reader_notation=lambda text: text,
    strip_logos_markup=lambda text: text,
    _scripture_matches=lambda text: [],
    public_reader_title=lambda title, slug=None: title,
    excerpt_paragraphs=lambda x: x.get("paras") or [],
    public_citation=lambda cite, work: cite,
    _plain_tag=lambda h: h,
)


def work(**over) -> dict:
    w = {"slug": "athanasius-on-the-incarnation", "title": "On the Incarnation", "author": "Athanasius",
         "has_audio": False, "related_topics": ["t1"], "first_english": False,
         "sections": [{"section": "1", "head": "", "english": ["In the beginning was the Word."]}]}
    w.update(over)
    return w


def content(works: list[dict], topic_title: str = "Grace") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        app_export.write(dist, Path(tmp), FAKE_B, works=works,
                         by_topic={"t1": [{"id": "x1", "author": "Athanasius", "paras": ["Grace is given."]}]},
                         topic_meta={"t1": {"title": topic_title, "locus_title": "Salvation"}},
                         tax={"loci": [{"topics": [{"id": "t1"}]}]}, sc_entries={}, wrong_cites={})
        catalog = json.loads((dist / "app" / "v1" / "catalog.json").read_text(encoding="utf-8"))
        body = (dist / "app" / "v1" / "works" / "athanasius-on-the-incarnation.json").read_text(encoding="utf-8")
        return {"content": catalog["content"], "body": body, "work": catalog["works"][0]}


class HeadTest(unittest.TestCase):
    def test_section_head_is_the_reader_heading(self):
        """The app (and the shelf files built from it) use display_head, the
        reader's H2 rule, never the raw head (Placeus worksheet tags)."""
        w = work(sections=[{"section": "1", "head": "On imputation GAR 3 tip", "english": ["Text."]}])
        body = json.loads(content([w])["body"])
        self.assertEqual(body["sections"][0]["head"], "On imputation")


class ContentDigestTest(unittest.TestCase):
    def test_same_input_same_digest(self) -> None:
        self.assertEqual(content([work()])["content"], content([work()])["content"])

    def test_audio_flag_alone_changes_digest(self) -> None:
        before, after = content([work()]), content([work(has_audio=True)])
        self.assertEqual(before["body"], after["body"])  # the text did not change
        self.assertEqual(before["work"]["hash"], after["work"]["hash"])
        self.assertNotEqual(before["content"], after["content"])

    def test_title_and_topics_change_digest(self) -> None:
        base = content([work()])["content"]
        self.assertNotEqual(base, content([work(title="De Incarnatione")])["content"])
        self.assertNotEqual(base, content([work(related_topics=[])])["content"])
        self.assertNotEqual(base, content([work()], topic_title="Divine grace")["content"])


class PartOnlyTest(unittest.TestCase):
    def test_partial_work_carries_part_only(self) -> None:
        row = content([work(scope="Homilies 5 and 6  of 50")])["work"]
        self.assertEqual(row["part_only"], "Homilies 5 and 6 of 50")

    def test_whole_work_has_no_part_only(self) -> None:
        self.assertNotIn("part_only", content([work()])["work"])
        self.assertNotIn("part_only", content([work(scope="  ")])["work"])

    def test_part_only_alone_changes_digest(self) -> None:
        self.assertNotEqual(content([work()])["content"], content([work(scope="Codices 1–17 of 279")])["content"])


if __name__ == "__main__":
    unittest.main()
