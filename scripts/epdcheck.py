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
"""Run solve.py over an external EPD suite of mate problems.

**Three outcomes, not two.** The obvious runner counts a row as a pass when the
mate distance matches the published one and a failure otherwise. That hides the
answer to the question the skill is actually asked. A position where a forced
mate is found at a longer distance than published is not a failure of "is there
a forced win" -- it is a correct verdict with an imprecise number, and it belongs
in its own column:

    shortest   a forced mate at the published distance or shorter
    longer     a forced mate, but further away than published
    none       no mate found: the honest failure

Collapsing "longer" into "none" makes the suite look worse than the skill is;
collapsing it into "shortest" makes it look better. Both readings mislead.

EPD input. One position per line, in either of the two common shapes:

    <board> <turn> <castling> <ep> bm #4;
    <board> <turn> <castling> <ep> dm 4;

Anything after a ``;`` is ignored, as are blank lines and ``#`` comments. Rows
with no mate distance are skipped and counted separately.

Usage:

    python3 scripts/epdcheck.py suite.epd
    python3 scripts/epdcheck.py suite.epd --limit 20 --sample 42
    python3 scripts/epdcheck.py suite.epd --budget 30 -v
"""

import argparse
import os
import random
import subprocess
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Reuse the verdict reader rather than writing a second one: two parsers of the
# same output drift apart, and the copy is always the one that rots.
from selftest import parse_output, solve, check_versions      # noqa: E402

DIST = re.compile(r"\b(?:bm\s*#|dm\s+)(-?\d+)")


def rows(path):
    """(fen, published_distance_or_None) per usable line.

    A negative distance means mate *against* the side to move -- matetrack has
    a few dozen of those. They are kept, not dropped: getting the sign wrong is
    a real failure mode and worth testing.

    EPD gives four fields and omits the halfmove and fullmove counters, which
    chess.Board requires. The fourth field is the en-passant square and must
    survive: a handful of matetrack problems are solved only by the en-passant
    capture, and padding it away turns them into different positions.
    """
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = DIST.search(line)
            head = line.split(";")[0].strip()
            fields = DIST.sub("", head).replace(" bm ", " ").split()
            if len(fields) < 2:
                continue
            while len(fields) < 4:
                fields.append("-")
            fen = " ".join(fields[:4]) + " 0 1"
            out.append((fen, int(m.group(1)) if m else None))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Run solve.py over an EPD suite")
    p.add_argument("epd", help="EPD file of mate problems")
    p.add_argument("--budget", type=float, default=30.0,
                   help="per-position budget in seconds")
    p.add_argument("--limit", type=int, default=None,
                   help="run at most this many positions")
    p.add_argument("--sample", type=int, default=None, metavar="SEED",
                   help="take --limit at random with this seed, "
                        "instead of the first N")
    p.add_argument("--extra", default="",
                   help="extra flags for solve.py, e.g. '--mate-probe 0' "
                        "to measure what the ladder is worth")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print every row, not only the ones with no mate")
    args = p.parse_args(argv)

    print(f"chess-verdict {check_versions()}\n")

    cases = [(f, d) for f, d in rows(args.epd) if d is not None]
    skipped = len(rows(args.epd)) - len(cases)
    if args.limit:
        if args.sample is not None:
            random.seed(args.sample)
            cases = random.sample(cases, min(args.limit, len(cases)))
        else:
            cases = cases[:args.limit]

    extra = args.extra.split() if args.extra else ()
    shortest = longer = none = 0
    started = time.time()

    for fen, want in cases:
        t0 = time.time()
        try:
            out = solve(fen, args.budget, extra)
        except subprocess.TimeoutExpired:
            out = ""
        got = parse_output(out)
        dt = time.time() - t0
        mate = got["mate"] if got and got["mate"] else None

        # want < 0 means mate against the side to move. A mate found for the
        # wrong side is not a near miss, it is the opposite answer, so the sign
        # has to agree before the distance is looked at.
        if mate is None or (mate > 0) != (want > 0):
            none += 1
            tag, detail = "none    ", f"published #{want}"
        elif abs(mate) <= abs(want):
            shortest += 1
            tag, detail = "shortest", f"#{mate} (published #{want})"
        else:
            longer += 1
            tag, detail = "longer  ", f"#{mate} (published #{want})"

        if args.verbose or mate is None:
            print(f"{tag}  {detail:24}  {dt:5.1f} s  {fen}")

    total = len(cases)
    took = time.time() - started
    print(f"\n{total} positions, {took:.0f} s"
          + (f", {skipped} skipped without a distance" if skipped else ""))
    print(f"  shortest  {shortest}")
    print(f"  longer    {longer}")
    print(f"  none      {none}")
    if total:
        found = shortest + longer
        print(f"\nA forced mate was found in {found}/{total} "
              f"({100 * found / total:.0f}%); of those, "
              f"{shortest} at the published distance or shorter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
