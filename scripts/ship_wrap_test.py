#!/usr/bin/env python3
"""ship.sh is one { ... } block, so editing it while a ship runs cannot change what the running ship executes
(9 Nov 2026: two edits landed on a running ship in one day; bash reads a plain script by byte offset).

  python3 scripts/ship_wrap_test.py
"""
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SHIP = Path(__file__).resolve().parent / "ship.sh"


def run_with_midrun_edit(body: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        script, out = Path(d) / "s.sh", Path(d) / "out.txt"
        script.write_text(body)
        with open(out, "w") as fh:
            proc = subprocess.Popen(["bash", str(script)], stdout=fh, stderr=subprocess.STDOUT)
            time.sleep(0.5)
            text = script.read_text().replace("#!/usr/bin/env bash\n", "#!/usr/bin/env bash\necho SHIFTED-BY-AN-EDIT-XXXXXXXXXXXXXXXX\n", 1)
            with open(script, "r+") as fh2:  # same inode, as an editor or git checkout of the same file can do
                fh2.write(text)
            proc.wait(timeout=20)
        return out.read_text()


class Wrap(unittest.TestCase):
    def test_plain_script_is_corrupted_by_a_midrun_edit(self):
        out = run_with_midrun_edit("#!/usr/bin/env bash\nsleep 1.5\necho two\necho three\n")
        self.assertIn("command not found", out)  # why the wrap exists

    def test_braced_script_ignores_a_midrun_edit(self):
        out = run_with_midrun_edit("#!/usr/bin/env bash\n{\nsleep 1.5\necho two\necho three\nexit $?\n}\n")
        self.assertEqual(out.split(), ["two", "three"])

    def test_ship_sh_is_wrapped(self):
        lines = SHIP.read_text().rstrip("\n").splitlines()
        body = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
        self.assertEqual(body[0], "set -euo pipefail")  # comments and the #! line are filtered out above
        self.assertEqual(body[1], "{", "ship.sh must open one { block right after set -euo pipefail")
        self.assertEqual(body[-2:], ["exit $?", "}"], "ship.sh must end with exit $? and the closing }")


if __name__ == "__main__":
    unittest.main()
