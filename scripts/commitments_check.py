#!/usr/bin/env python3
"""Promise clock for Via Patrum (owner 9 Nov 2026: "sync everything we can so we avoid drift"; same rule as SaneCite's
tools/commitments_check.py, SOP S3).

Every OPEN row of the ledger (outputs/viapatrum/COMMITMENTS.md, private: it names the people we wrote to) carries a
due tag in its Status cell:
  due 2026-11-16      a date; the check fails once today is past it while the row is still OPEN
  due standing        an ongoing rule (a licence, free downloads)
  due on reply        owed once the other person answers
  due on funding      owed only once money arrives
To clear a failure, keep the promise and mark the row KEPT, or mark it BROKEN or CHANGED with the date and what
changed. Never just move the date without saying why in the row.

  python3 scripts/commitments_check.py [--today YYYY-MM-DD] [--file PATH] [--alert]

--alert writes outputs/agent-alerts/viapatrum-commitments.md while there is a problem (the ship runs it; it never
blocks a ship, because readers should still get corrections while a promise is late).
Exit 0 ok, 1 problems, 2 no ledger.
"""
import datetime
import os
import re
import sys

LEDGER = os.path.expanduser("~/SaneApps/outputs/viapatrum/COMMITMENTS.md")
ALERT = os.path.expanduser("~/SaneApps/outputs/agent-alerts/viapatrum-commitments.md")
DUE = re.compile(r"\bdue (\d{4}-\d\d-\d\d|standing|on reply|on funding)\b", re.I)


def problems(text: str, today: str) -> list[str]:
    out, rows = [], 0
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        rows += 1
        num, status = cells[0], cells[-1]
        if not status.upper().startswith("OPEN"):
            continue
        m = DUE.search(status)
        if not m:
            out.append(f"row {num} is OPEN with no due tag (add 'due YYYY-MM-DD', 'due standing', 'due on reply' "
                       "or 'due on funding')")
        elif m.group(1)[0].isdigit() and m.group(1) < today:
            out.append(f"row {num} was due {m.group(1)} and is still OPEN: keep it and mark KEPT, or mark BROKEN/CHANGED "
                       f"with the date ({cells[1]}: {cells[3][:90]})")
    if rows == 0:
        out.append("no ledger rows found: the table format changed or the file is wrong")
    return out


def write_alert(found: list[str], path: str = ALERT, ledger: str = LEDGER) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = "\n".join(f"- {p}" for p in found)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Via Patrum: a promise is overdue or untracked\n\nRaised: {datetime.datetime.now():%Y-%m-%d %I:%M %p}"
                 f" by scripts/commitments_check.py (viapatrum.org ship).\nLedger: {ledger}\n\n{body}\n\n"
                 "Fix: keep the promise and mark the row KEPT, or mark it BROKEN/CHANGED with the date and what changed."
                 " Then move this file to done/.\n")


def main(argv: list[str]) -> int:
    today = argv[argv.index("--today") + 1] if "--today" in argv else datetime.date.today().isoformat()
    path = argv[argv.index("--file") + 1] if "--file" in argv else LEDGER
    if not os.path.exists(path):
        print(f"commitments_check: no ledger at {path}")
        return 2
    found = problems(open(path, encoding="utf-8").read(), today)
    for p in found:
        print("commitments_check:", p)
    print("commitments_check:", "ok" if not found else f"{len(found)} problem(s)")
    if found and "--alert" in argv:
        write_alert(found, ledger=path)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
