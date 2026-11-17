"""refresh_zwi.sign_groups: works already in the live set are signed again with --resign; new works get a first
signature without it (17 Nov 2026: a new work sent with --resign was refused and blocked every archive update).
No network, no signing."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refresh_zwi as R  # noqa: E402


class SignGroups(unittest.TestCase):
    def test_new_works_are_not_sent_with_resign(self):
        with tempfile.TemporaryDirectory() as d:
            live = Path(d)
            (live / "didache.zwi").write_bytes(b"x")
            (live / "polycarp.zwi").write_bytes(b"x")
            groups = R.sign_groups({"polycarp", "hermas-shepherd", "didache", "gregory-nazianzus-oration-34"}, live)
        self.assertEqual(groups, [(["didache", "polycarp"], " --resign"),
                                  (["gregory-nazianzus-oration-34", "hermas-shepherd"], "")])

    def test_only_resigns_or_only_new_gives_one_group(self):
        with tempfile.TemporaryDirectory() as d:
            live = Path(d)
            (live / "didache.zwi").write_bytes(b"x")
            self.assertEqual(R.sign_groups({"didache"}, live), [(["didache"], " --resign")])
            self.assertEqual(R.sign_groups({"hermas-shepherd"}, live), [(["hermas-shepherd"], "")])
            self.assertEqual(R.sign_groups(set(), live), [])


if __name__ == "__main__":
    unittest.main()
