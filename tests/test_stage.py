#!/usr/bin/env python3
#
# chess-verdict -- a Stockfish verdict on a chess position
# Copyright (C) 2026  Pavel Kurochka <https://github.com/PavelKurochka>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Tests for the timing journal's stop mark (stage.py --stop).

Run directly; no framework, no network, about four seconds:

    python3 tests/test_stage.py

Each test drives stage.py as a subprocess against a throwaway journal, because
the thing under test is the file format and the command-line surface, not the
functions. The idle intervals are real sleeps -- the bug this file exists to
catch was entirely about wall-clock time being attributed to the wrong side of a
mark, and a mocked clock would have reproduced the old behaviour just as happily.
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(HERE, os.pardir, "scripts", "stage.py")

failures = []


def stage(journal, *args):
    env = dict(os.environ, CHESS_TIMELINE=journal)
    r = subprocess.run([sys.executable, STAGE, *args],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout, r.stderr


def total_of(report):
    m = re.search(r"^\s*TOTAL\s+([\d.]+) s", report, re.M)
    return float(m.group(1)) if m else None


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


def fresh():
    fd, path = tempfile.mkstemp(suffix=".tsv")
    os.close(fd)
    os.remove(path)
    return path


def test_stop_excludes_idle():
    """The whole point: time after --stop is not part of the total."""
    j = fresh()
    stage(j, "--start")
    stage(j, "work", "--", "sleep", "0.4")
    stage(j, "--stop")
    _, before, _ = stage(j, "--report")
    subprocess.run([sys.executable, "-c", "import time; time.sleep(1.5)"])
    _, after, _ = stage(j, "--report")
    t1, t2 = total_of(before), total_of(after)
    check("idle time after --stop is excluded",
          t1 is not None and t2 is not None and abs(t2 - t1) < 0.2,
          f"{t1} s then {t2} s")
    check("the total is the work, not the wall clock",
          t2 is not None and t2 < 1.0, f"{t2} s")


def test_coverage_lines():
    """A journal that was never stopped must say so."""
    j = fresh()
    stage(j, "--start")
    stage(j, "work", "--", "sleep", "0.1")
    _, open_report, _ = stage(j, "--report")
    check("an unstopped journal warns in its coverage line",
          "never closed with --stop" in open_report)
    stage(j, "--stop")
    _, closed_report, _ = stage(j, "--report")
    check("a stopped journal claims coverage to the end of the work",
          "end of the work" in closed_report
          and "never closed" not in closed_report)


def test_later_command_cancels_stop():
    """A follow-up question reopens the journal without anyone undoing anything."""
    j = fresh()
    stage(j, "--start")
    stage(j, "first", "--", "sleep", "0.1")
    stage(j, "--stop")
    subprocess.run([sys.executable, "-c", "import time; time.sleep(0.6)"])
    stage(j, "second", "--", "sleep", "0.1")
    _, report, _ = stage(j, "--report")
    check("a command after --stop cancels it",
          "never closed with --stop" in report)
    check("the follow-up gap is then counted",
          (total_of(report) or 0) > 0.6, f"{total_of(report)} s")
    stage(j, "--stop")
    _, report2, _ = stage(j, "--report")
    check("stopping again closes it once more", "end of the work" in report2)


def test_stop_closes_open_bracket():
    """A --begin with no --end would otherwise vanish from the table."""
    j = fresh()
    stage(j, "--start")
    stage(j, "--begin", "reading the diagram")
    subprocess.run([sys.executable, "-c", "import time; time.sleep(0.3)"])
    stage(j, "--stop")
    _, report, _ = stage(j, "--report")
    check("an open bracket survives as a measured row",
          "reading the diagram" in report and "closed by --stop" in report)
    # Check the number, not its spelling: the first version of this pinned the
    # duration with a regex for "0.2" or "0.3" and failed on a loaded machine
    # where the same 0.3 s sleep was measured at 0.4 s.
    m = re.search(r"reading the diagram.*?([\d.]+) s", report)
    check("and it carries a real duration",
          m is not None and float(m.group(1)) >= 0.25,
          m.group(1) + " s" if m else "no row")


def test_at_last_repairs():
    """--at-last recovers a session where the stop was forgotten."""
    j = fresh()
    stage(j, "--start")
    stage(j, "work", "--", "sleep", "0.3")
    subprocess.run([sys.executable, "-c", "import time; time.sleep(1.5)"])
    _, forgotten, _ = stage(j, "--report")
    stage(j, "--stop", "--at-last")
    _, repaired, _ = stage(j, "--report")
    check("the forgotten journal had the idle time in it",
          (total_of(forgotten) or 0) > 1.5, f"{total_of(forgotten)} s")
    check("--at-last backdates the mark to the last row",
          (total_of(repaired) or 99) < 0.6, f"{total_of(repaired)} s")


def test_gap_breakdown():
    """An idle stretch is named after the command it sat in front of.

    The fixture puts the whole gap in one place -- a single 1.2 s pause between
    two 0.2 s commands -- because the failure this guards against is not a wrong
    total but a right total attributed to the wrong command. A gap spread evenly
    over several commands would pass a broken implementation just as happily.
    """
    j = fresh()
    stage(j, "--start")
    stage(j, "first", "--", "sleep", "0.2")
    subprocess.run([sys.executable, "-c", "import time; time.sleep(1.2)"])
    stage(j, "second", "--", "sleep", "0.2")
    stage(j, "--stop")
    _, rep, _ = stage(j, "--report")

    m = re.search(r"^\s+before second\s+([\d.]+) s\s*$", rep, re.M)
    named = float(m.group(1)) if m else None
    check("the idle stretch is named after the command that followed it",
          named is not None and 1.0 < named < 1.7, f"{named} s")
    check("the idle stretch is not charged to the command before it",
          not re.search(r"^\s+before first\s+[1-9][\d.]* s\s*$", rep, re.M))

    listed = [float(x) for x in
              re.findall(r"^\s+(?:before .+?|after the last command)\s+([\d.]+) s\s*$",
                         rep, re.M)]
    pooled = re.search(r"^\s+other: gaps.*?([\d.]+) s", rep, re.M)
    pooled = float(pooled.group(1)) if pooled else None
    check("the breakdown accounts for the pooled remainder",
          pooled is not None and listed
          and abs(sum(listed) - pooled) < 0.2,
          f"{sum(listed):.1f} s of {pooled} s in {len(listed)} line(s)")


def test_stop_without_journal():
    j = fresh()
    code, _, err = stage(j, "--stop")
    check("--stop without --start is an error, not a silent no-op",
          code == 2 and "--start" in err)


if __name__ == "__main__":
    for fn in (test_stop_excludes_idle, test_coverage_lines,
               test_later_command_cancels_stop, test_stop_closes_open_bracket,
               test_at_last_repairs, test_gap_breakdown,
               test_stop_without_journal):
        fn()
    print()
    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")
