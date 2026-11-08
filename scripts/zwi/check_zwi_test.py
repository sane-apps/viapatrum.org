"""ZWI 1.5 checks with known answers: a good file passes; each broken one fails for the stated reason.

Archives are made here with a throwaway P-384 key, so no real key is touched. The end-to-end test runs the real
signer (sign_zwi.mjs, through node) and packer on a staged re-sign made by build_zwi.previous_version.

Run: <venv with cryptography + beautifulsoup4>/bin/python -m unittest scripts/zwi/check_zwi_test.py
     (8 Nov 2026: ~/SaneApps/outputs/viapatrum/zwi-20261106/tools/venv)
"""
import base64
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_zwi as C  # noqa: E402

from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature  # noqa: E402

KID = "did:psqr:viapatrum.org#publish"
SLUG = "augustine-care-for-the-dead"


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def png(size: int = 64) -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


KEY = ec.generate_private_key(ec.SECP384R1())
OTHER_KEY = ec.generate_private_key(ec.SECP384R1())


def jwk_public(key) -> dict:
    n = key.public_key().public_numbers()
    return {"kid": KID, "kty": "EC", "crv": "P-384", "x": b64u(n.x.to_bytes(48, "big")),
            "y": b64u(n.y.to_bytes(48, "big"))}


IDENTITY = {"psqr": {"publicKeys": [jwk_public(KEY)]}}
KEYS = C.load_keys(IDENTITY)


def sign(meta_b: bytes, media_b: bytes, iat: int, previous: str | None = None, key=KEY, kid=KID) -> bytes:
    payload = {"iss": "Via Patrum", "address": "https://viapatrum.org", "iat": iat,
               "metadata": sha1(meta_b), "media": sha1(media_b)}
    if previous is not None:
        payload["previous"] = previous
    inp = f"{b64u(json.dumps({'alg': 'ES384', 'kid': kid, 'typ': 'JWT'}).encode())}.{b64u(json.dumps(payload).encode())}"
    r, s = decode_dss_signature(key.sign(inp.encode(), ec.ECDSA(hashes.SHA384())))
    sig = r.to_bytes(48, "big") + s.to_bytes(48, "big")
    import datetime as dt
    updated = dt.datetime.fromtimestamp(iat, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000")
    return (json.dumps({"identityName": "Via Patrum", "identityAddress": "https://viapatrum.org", "kid": kid,
                        "updated": updated, "alg": "ES384", "token": f"{inp}.{b64u(sig)}"}, indent=2) + "\n").encode()


HTML = (b'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>T</title></head><body>'
        b'<nav><a href="#s1">One</a></nav><section id="s1"><h2>One</h2><p>Text.</p></section></body></html>')
TXT = b"On Care for the Dead\n\nText.\n"
WORK = {"ID": SLUG, "Title": {"Title": "On Care for the Dead", "Lang": "en"},
        "OtherTitles": [{"Title": "De cura pro mortuis gerenda", "Lang": "la"}], "Lang": "la",
        "Author": "Augustine of Hippo", "AuthorDates": {"Born": 354, "Died": 430}}
T0 = 1794006778


def meta_v13(html=HTML, txt=TXT) -> dict:
    return {"ZWIversion": 1.3, "Title": "On Care for the Dead", "Lang": "en", "Publisher": "viapatrum",
            "CollectionTitle": "Via Patrum", "Primary": "article.html",
            "Content": {"article.html": sha1(html), "article.txt": sha1(txt)},
            "TimeCreated": str(T0), "LastModified": str(T0), "Description": "Text.", "License": "CC BY 4.0",
            "SourceURL": f"https://viapatrum.org/works/{SLUG}/"}


def meta_v15(**over) -> dict:
    m = {**meta_v13(), "ZWIversion": 1.5, "TimeCreated": T0, "LastModified": T0 + 172800, "Work": WORK,
         "VersionNote": "Re-signed to ZWI 1.5: adds the Work field and numeric times; text unchanged."}
    m.update(over)
    return {k: v for k, v in m.items() if v is not None}


def dumps(d: dict) -> bytes:
    return (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode()


COLICON = png()
MEDIA = dumps({"data/colicon.png": sha1(COLICON)})


def zip_files(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


def v1_files() -> dict:
    m = dumps(meta_v13())
    return {"article.html": HTML, "article.txt": TXT, "metadata.json": m, "media.json": MEDIA,
            "data/colicon.png": COLICON, "signature.json": sign(m, MEDIA, T0 + 33)}


def resign(old: dict, meta: dict, previous: str | None = "auto", key=KEY) -> dict:
    """The spec's re-sign steps: old signature/metadata/media into history/<n>/, new metadata, sign with previous."""
    hist = {n: b for n, b in old.items() if n.startswith("history/")}
    n = len({x.split("/")[1] for x in hist}) + 1
    for f in ("signature.json", "metadata.json", "media.json"):
        hist[f"history/{n}/{f}"] = old[f]
    m = dumps(meta)
    prev = sha1(old["signature.json"]) if previous == "auto" else previous
    new = {k: v for k, v in old.items() if not k.startswith("history/")}
    new.update({"metadata.json": m, "signature.json": sign(m, MEDIA, T0 + 172900, prev, key), **hist})
    return new


def check(files: dict, warnings=None) -> list[str]:
    return C.check_archive(zip_files(files), SLUG, KEYS, None, None, None, warnings)


class GoodFiles(unittest.TestCase):
    def test_first_signed_13_file_passes(self):
        self.assertEqual(check(v1_files()), [])

    def test_resigned_15_file_passes(self):
        self.assertEqual(check(resign(v1_files(), meta_v15())), [])

    def test_two_resigns_pass(self):
        v2 = resign(v1_files(), meta_v15())
        v3 = resign(v2, meta_v15(VersionNote="Text corrected in section 1."))
        self.assertEqual(check(v3), [])
        self.assertIn("history/2/signature.json", v3)

    def test_previous_archive_compare_passes(self):
        v1 = v1_files()
        errs = C.check_archive(zip_files(resign(v1, meta_v15())), SLUG, KEYS, None, zip_files(v1), 1.5)
        self.assertEqual(errs, [])


class BrokenHistory(unittest.TestCase):
    def assertFails(self, files, needle):
        errs = check(files)
        self.assertTrue(any(needle in e for e in errs), f"{needle!r} not in {errs}")

    def test_tampered_history_metadata(self):
        f = resign(v1_files(), meta_v15())
        hm = json.loads(f["history/1/metadata.json"])
        hm["Title"] = "Altered"
        f["history/1/metadata.json"] = dumps(hm)
        self.assertFails(f, "history/1: token metadata hash does not match")

    def test_tampered_history_signature(self):
        f = resign(v1_files(), meta_v15())
        f["history/1/signature.json"] = f["history/1/signature.json"].replace(b'"Via Patrum"', b'"Via  Patrum"', 1)
        self.assertFails(f, "previous in signature.json is not the SHA-1 of history/1/signature.json")

    def test_missing_version_note(self):
        self.assertFails(resign(v1_files(), meta_v15(VersionNote=None)), "no VersionNote")

    def test_wrong_previous(self):
        self.assertFails(resign(v1_files(), meta_v15(), previous="0" * 40), "previous in signature.json")

    def test_no_previous_in_resigned_token(self):
        self.assertFails(resign(v1_files(), meta_v15(), previous=None), "previous in signature.json")

    def test_previous_without_history(self):
        f = resign(v1_files(), meta_v15())
        for n in [n for n in f if n.startswith("history/")]:
            del f[n]
        self.assertFails(f, "token has previous but there is no history")

    def test_folder_gap(self):
        f = resign(v1_files(), meta_v15())
        f = {n.replace("history/1/", "history/2/"): b for n, b in f.items()}
        self.assertFails(f, "history folders are [2], not 1..1")

    def test_extra_file_in_history(self):
        f = resign(v1_files(), meta_v15())
        f["history/1/article.txt"] = TXT
        self.assertFails(f, "unexpected file in history: history/1/article.txt")

    def test_media_missing_from_history(self):
        f = resign(v1_files(), meta_v15())
        del f["history/1/media.json"]
        self.assertFails(f, "history/1: token has media but there is no media.json")

    def test_time_created_changed(self):
        self.assertFails(resign(v1_files(), meta_v15(TimeCreated=T0 + 5)), "TimeCreated differs")

    def test_history_1_with_previous(self):
        v1 = v1_files()
        v1["signature.json"] = sign(v1["metadata.json"], MEDIA, T0 + 33, previous="1" * 40)
        self.assertFails(resign(v1, meta_v15()), "history/1 token has previous")

    def test_middle_version_without_note(self):
        v2 = resign(v1_files(), meta_v15(VersionNote=None))
        v3 = resign(v2, meta_v15(VersionNote="Second change."))
        self.assertFails(v3, "history/2/metadata.json has no VersionNote")

    def test_unknown_key_is_unverifiable_not_invalid(self):
        v1 = v1_files()
        v1["signature.json"] = sign(v1["metadata.json"], MEDIA, T0 + 33, key=OTHER_KEY,
                                    kid="did:psqr:gone.example#publish")
        warns = []
        self.assertEqual(check(resign(v1, meta_v15()), warns), [])
        self.assertTrue(warns and "unverifiable" in warns[0])

    def test_history_signed_by_wrong_key_fails(self):
        v1 = v1_files()
        v1["signature.json"] = sign(v1["metadata.json"], MEDIA, T0 + 33, key=OTHER_KEY)
        self.assertFails(resign(v1, meta_v15()), "history/1: signature does not verify")

    def test_previous_archive_not_kept(self):
        v1 = v1_files()
        other = dict(v1)
        other["signature.json"] = sign(v1["metadata.json"], MEDIA, T0 + 99)
        errs = C.check_archive(zip_files(resign(other, meta_v15())), SLUG, KEYS, None, zip_files(v1), None)
        self.assertIn("history/1/signature.json is not the previous archive's signature.json byte for byte", errs)


class Fields15(unittest.TestCase):
    def fails(self, meta, needle):
        errs = check(resign(v1_files(), meta))
        self.assertTrue(any(needle in e for e in errs), f"{needle!r} not in {errs}")

    def test_bad_work_ids(self):
        for bad in ("Augustine-Care", "augustine--care", "augustine_care", "-augustine", "augustine-", ""):
            self.fails(meta_v15(Work={**WORK, "ID": bad}), "does not match ^[a-z0-9]+(-[a-z0-9]+)*$")

    def test_work_lang_must_be_single(self):
        self.fails(meta_v15(Work={**WORK, "Lang": ["la", "grc"]}), "Work: Lang is not a single language code")

    def test_top_level_lang_array_ok(self):
        self.assertEqual(check(resign(v1_files(), meta_v15(Lang=["en", "la"]))), [])

    def test_circa_without_year(self):
        self.fails(meta_v15(Work={**WORK, "AuthorDates": {"DiedCirca": True, "Born": 354}}),
                   "DiedCirca without Died")

    def test_year_not_integer(self):
        self.fails(meta_v15(Work={**WORK, "AuthorDates": {"Born": "354"}}), "Born is not a nonzero integer")
        self.fails(meta_v15(Work={**WORK, "AuthorDates": {"Born": 0}}), "Born is not a nonzero integer")

    def test_bc_years_ok(self):
        socrates = {"Born": -470, "BornCirca": True, "Died": -399}
        self.assertEqual(check(resign(v1_files(), meta_v15(Work={**WORK, "AuthorDates": socrates}))), [])

    def test_string_times_fail_in_15(self):
        self.fails(meta_v15(TimeCreated=str(T0)), "TimeCreated is not a number")

    def test_string_times_ok_in_13(self):
        self.assertEqual(check(v1_files()), [])  # 1.3 file with "TimeCreated": "1794006778"

    def test_title_shape(self):
        self.fails(meta_v15(Work={**WORK, "Title": "On Care for the Dead"}), "Title is not")

    def test_require_version(self):
        errs = C.check_archive(zip_files(v1_files()), SLUG, KEYS, None, None, 1.5)
        self.assertIn("ZWIversion is 1.3, not 1.5", errs)


class Collection(unittest.TestCase):
    def test_files_of_one_work_share_the_block(self):
        other = {**WORK, "Title": {"Title": "Book 2", "Lang": "en"}}
        self.assertEqual(C.check_work_consistency({"a": WORK, "b": dict(WORK), "c": {**WORK, "ID": "other"}}), {})
        errs = C.check_work_consistency({"a": WORK, "b": other})
        self.assertEqual(list(errs), ["b"])
        self.assertIn("differs from the Work block in a", errs["b"][0])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class EndToEnd(unittest.TestCase):
    """build_zwi.previous_version -> sign_zwi.mjs -> pack_zwi.py -> check_zwi, with a test key."""

    def test_resign_pipeline(self):
        import build_zwi as B
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            old_dir = td / "old"
            old_dir.mkdir()
            v1 = v1_files()
            (old_dir / f"{SLUG}.zwi").write_bytes(zip_files(v1))
            prev = B.previous_version(old_dir / f"{SLUG}.zwi")
            self.assertEqual(prev["n"], 1)
            stage = td / "stage" / SLUG
            for rel, b in {**prev["history"], "article.html": HTML, "article.txt": TXT, "media.json": MEDIA,
                           "data/colicon.png": COLICON, "metadata.json": dumps(meta_v15())}.items():
                (stage / rel).parent.mkdir(parents=True, exist_ok=True)
                (stage / rel).write_bytes(b)
            n = KEY.private_numbers()
            jwk = {**jwk_public(KEY), "d": b64u(n.private_value.to_bytes(48, "big"))}
            env = {**os.environ, "VIAPATRUM_PSQR_PUBLISH_JWK": json.dumps(jwk)}
            r = subprocess.run(["node", str(HERE / "sign_zwi.mjs"), "--stage", str(td / "stage"), "--resign"],
                               env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"with_previous":1', r.stdout)
            r = subprocess.run([sys.executable, str(HERE / "pack_zwi.py"), "--stage", str(td / "stage"),
                                "--out", str(td / "out")], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            data = (td / "out" / f"{SLUG}.zwi").read_bytes()
            self.assertEqual(C.check_archive(data, SLUG, KEYS, None, zip_files(v1), 1.5), [])
            z = zipfile.ZipFile(io.BytesIO(data))
            self.assertEqual(z.read("history/1/signature.json"), v1["signature.json"])

    def test_resign_refuses_folder_without_history(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "stage" / SLUG
            stage.mkdir(parents=True)
            (stage / "metadata.json").write_bytes(dumps(meta_v15(VersionNote=None)))
            (stage / "media.json").write_bytes(MEDIA)
            n = KEY.private_numbers()
            jwk = {**jwk_public(KEY), "d": b64u(n.private_value.to_bytes(48, "big"))}
            env = {**os.environ, "VIAPATRUM_PSQR_PUBLISH_JWK": json.dumps(jwk)}
            r = subprocess.run(["node", str(HERE / "sign_zwi.mjs"), "--stage", str(Path(td) / "stage"), "--resign"],
                               env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 1)
            self.assertIn("--resign: no history/", r.stderr)
            self.assertFalse((stage / "signature.json").exists())


if __name__ == "__main__":
    unittest.main()
