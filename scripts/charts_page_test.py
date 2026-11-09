#!/usr/bin/env python3
"""Charts (/charts/fathers/): the data assembly places dated Fathers in the
right lane, leaves undated ones off (and names them), puts work dots at the
works' own dates, and the places file still quotes each Father's bio.
Run: python3 -B scripts/charts_page_test.py"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts_page as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

DATES = {
    "polycarp-of-smyrna": "c. 69–c. 155",
    "cyprian": "c. 200–258",
    "origen": "c. 185–c. 254",
    "ignatius-of-antioch": "d. c. 110",
    "hesychius-of-jerusalem": "fl. c. 412–450",
    "oecumenius": "fl. 6th century",
    "georgius-peccator": "",
    "didache": "c. 100",
    "john-wesley": "1703–1791",
    "lactantius": "c. 250–c. 325",
}
PLACES = {
    "meta": {"lanes": [["west", "Rome and the West"], ["africa", "North Africa"], ["egypt", "Alexandria and Egypt"],
                       ["palestine", "Palestine and Cyprus"], ["syria", "Antioch and Syria"],
                       ["asia-minor", "Asia Minor and Greece"]]},
    "fathers": {"polycarp-of-smyrna": {"lane": "asia-minor"}, "cyprian": {"lane": "africa"},
                "origen": {"lane": "egypt"}, "ignatius-of-antioch": {"lane": "syria"},
                "hesychius-of-jerusalem": {"lane": "palestine"}, "oecumenius": {"lane": "asia-minor"}},
    "no_place": ["lactantius"],
    "texts": ["didache"],
}
HUBS = [{"slug": s, "name": s.replace("-", " ").title()} for s in DATES]
WORKS = [
    {"slug": "origen-on-prayer", "title": "On Prayer", "author_slug": "origen", "period": "c. 233–235"},
    {"slug": "origen-hom-a", "title": "Homily A", "author_slug": "origen", "period": "c. 230–250"},
    {"slug": "origen-hom-b", "title": "Homily B", "author_slug": "origen", "period": "c. 230–250"},
    {"slug": "origen-life", "title": "Life-dated", "author_slug": "origen", "period": "c. 185–c. 254"},
    {"slug": "origen-cent", "title": "Century", "author_slug": "origen", "period": "3rd century"},
    {"slug": "origen-guess", "title": "Guess", "author_slug": "origen", "period": "c. 240?"},
    {"slug": "cyprian-unity", "title": "On the Unity of the Church", "author_slug": "cyprian", "period": "251"},
    {"slug": "cyprian-print", "title": "Printed later", "author_slug": "cyprian", "period": "1682"},
    {"slug": "polycarp-phil", "title": "To the Philippians", "author_slug": "polycarp-of-smyrna", "period": "c. 69–c. 155"},
    {"slug": "polycarp-young", "title": "Too early", "author_slug": "polycarp-of-smyrna", "period": "c. 75"},
]


def assemble():
    return C.assemble(HUBS, WORKS, PLACES, [], lambda n, s: DATES.get(s, ""),
                      lambda n, s: (DATES.get(s) + " AD") if DATES.get(s) else "")


class ParseLifeTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(C.parse_life("c. 69–c. 155"), {"kind": "life", "start": 69, "end": 155})
        self.assertEqual(C.parse_life("c. 293/298–373"), {"kind": "life", "start": 293, "end": 373})
        self.assertEqual(C.parse_life("c. 759–817/818"), {"kind": "life", "start": 759, "end": 818})
        self.assertEqual(C.parse_life("354–430 AD"), {"kind": "life", "start": 354, "end": 430})
        self.assertEqual(C.parse_life("d. c. 110"), {"kind": "death", "start": 110, "end": 110})
        self.assertEqual(C.parse_life("fl. c. 177"), {"kind": "point", "start": 177, "end": 177})
        self.assertEqual(C.parse_life("fl. c. 190–211"), {"kind": "fl", "start": 190, "end": 211})

    def test_unplaceable(self):
        for raw in ("", None, "fl. 6th century", "3rd century", "fl. early 6th century", "between 343 and 381",
                    "fl. 4th–5th century"):
            self.assertIsNone(C.parse_life(raw), raw)


class WorkDateTests(unittest.TestCase):
    life = {"kind": "life", "start": 185, "end": 254}

    def test_own_date_is_a_dot(self):
        d = C.work_date("c. 230–250", "c. 185–c. 254", self.life)
        self.assertEqual((d["lo"], d["hi"], d["year"], d["label"]), (230, 250, 240, "c. 230–250 AD"))
        self.assertEqual(C.work_date("c. 248", "c. 185–c. 254", self.life)["year"], 248)

    def test_no_dot_without_a_date_of_its_own(self):
        for p in ("c. 185–c. 254", "", "3rd century", "c. 240?", "before c. 250", "c. 9th cent.",
                  "1700 (London reprint)", "c. 190"):
            self.assertIsNone(C.work_date(p, "c. 185–c. 254", self.life), p)

    def test_floruit_writer_keeps_later_dates(self):
        # "fl. c. 390" is a working year, not a death: c. 390–400 still dates the work.
        d = C.work_date("c. 390–400", "fl. c. 390", {"kind": "point", "start": 390, "end": 390})
        self.assertEqual(d["year"], 395)


class AssembleTests(unittest.TestCase):
    def setUp(self):
        self.data = assemble()
        self.lanes = {lane["id"]: lane for lane in self.data["lanes"]}
        self.by_slug = {f["slug"]: f for lane in self.data["lanes"] for f in lane["fathers"]}

    def test_dated_fathers_in_their_lanes(self):
        self.assertEqual([f["slug"] for f in self.lanes["egypt"]["fathers"]], ["origen"])
        self.assertEqual([f["slug"] for f in self.lanes["africa"]["fathers"]], ["cyprian"])
        self.assertEqual([f["slug"] for f in self.lanes["asia-minor"]["fathers"]], ["polycarp-of-smyrna"])
        self.assertEqual(self.lanes["syria"]["fathers"][0]["kind"], "death")
        self.assertEqual(self.lanes["palestine"]["fathers"][0]["kind"], "fl")
        self.assertNotIn("west", self.lanes, "an empty lane is not drawn")
        self.assertEqual(self.by_slug["origen"]["dates"], "c. 185–c. 254 AD")
        self.assertEqual(self.by_slug["origen"]["href"], "/authors/origen/")

    def test_undated_left_off_and_named(self):
        off = {k: [r["slug"] for r in v] for k, v in self.data["off"].items()}
        self.assertEqual(off["century"], ["oecumenius"])
        self.assertEqual(off["undated"], ["georgius-peccator"])
        self.assertEqual(off["no_place"], ["lactantius"])
        self.assertEqual(off["texts"], ["didache"])
        self.assertEqual(off["later"], ["john-wesley"])
        for slug in ("oecumenius", "georgius-peccator", "lactantius", "didache", "john-wesley"):
            self.assertNotIn(slug, self.by_slug)
        html = C.off_html(self.data)
        self.assertIn('href="/authors/oecumenius/"', html)
        self.assertIn("fl. 6th century AD", html)

    def test_work_dots_at_their_dates(self):
        dots = self.by_slug["origen"]["dots"]
        self.assertEqual([(g["year"], g["label"], len(g["titles"])) for g in dots],
                         [(234, "c. 233–235 AD", 1), (240, "c. 230–250 AD", 2)])
        self.assertEqual(self.by_slug["origen"]["works"], 6)
        self.assertEqual(self.by_slug["origen"]["dated_works"], 3)
        self.assertEqual([g["year"] for g in self.by_slug["cyprian"]["dots"]], [251], "a 1682 printing is no dot")
        self.assertEqual(self.by_slug["polycarp-of-smyrna"]["dots"], [], "life-only and too-early dates are no dots")
        self.assertEqual(self.data["counts"], {"fathers": 5, "works": 10, "dated_works": 4})

    def test_rendered_bars_are_links_with_dates(self):
        html = C.chart_body(self.data)
        self.assertEqual(html.count('class="fc-bar'), 5)
        self.assertIn('<a class="fc-bar is-life" href="/authors/origen/"', html)
        self.assertIn('<span class="fc-dates">c. 185–c. 254 AD', html)
        self.assertIn('style="--d:240"', html)
        self.assertIn('id="fc-list"', html)

    def test_pack_never_overlaps(self):
        items = [{"x0": a, "x1": b} for a, b in [(100, 200), (150, 180), (210, 300), (190, 260), (310, 320)]]
        rows = C.pack(items)
        self.assertEqual(rows, 2)
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a["row"] == b["row"]:
                    self.assertTrue(a["x1"] <= b["x0"] or b["x1"] <= a["x0"])


class DataFileTests(unittest.TestCase):
    def test_places_quote_each_bio(self):
        places = C.load_places()
        bios = json.loads((ROOT / "data" / "author-bios.json").read_text(encoding="utf-8"))
        lanes = {lid for lid, _ in places["meta"]["lanes"]}
        for slug, v in places["fathers"].items():
            self.assertIn(v["lane"], lanes, slug)
            self.assertIn(v["basis"], (bios.get(slug) or {}).get("bio", ""), f"{slug}: basis not in its bio")
        listed = set(places["fathers"])
        self.assertFalse(listed & set(places["no_place"]))
        self.assertFalse(listed & set(places["texts"]))

    def test_seven_councils_from_creeds_data(self):
        cs = C.load_councils()
        self.assertEqual([c["start"] for c in cs], [325, 381, 431, 451, 553, 680, 787])
        self.assertEqual(cs[5]["dates"], "680–681 AD")
        self.assertTrue(all(c["href"].startswith("/creeds/#c-") for c in cs))


if __name__ == "__main__":
    unittest.main()
