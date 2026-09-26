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
"""Tests for the verdict rule that compares the headline against the replies.

    python3 tests/test_verdict.py

The bug these exist to catch: a reply that is mated proves the position mates
at least down that branch, so a centipawn headline alongside a majority of
mated replies is an unresolved search, not a verdict. That rule was written
twice -- once for the full enumeration, once for the sampled defences -- and
the two copies disagreed on `8/8/8/4b1p1/5pP1/R3k2P/3p4/5K2 b`, a mate in 13
where eleven of twelve replies are mated and the twelfth is the toughest.

These call the predicate directly rather than running a search: the engine's
depth on the day must not decide whether the test passes.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "scripts"))

import chess.engine  # noqa: E402

import solve  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}"
          f"{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


CP = chess.engine.Cp
MATE = chess.engine.Mate

# --- winning_mates -----------------------------------------------------------

check("a mate for the attacker counts",
      len(solve.winning_mates([MATE(4)])) == 1)

check("a mate against the attacker does not",
      len(solve.winning_mates([MATE(-4)])) == 0)

check("Mate(0) -- mate received -- does not",
      len(solve.winning_mates([MATE(0)])) == 0)

check("MateGiven counts",
      len(solve.winning_mates([chess.engine.MateGiven])) == 1,
      "the reply is already checkmate on the board")

check("a centipawn score does not",
      len(solve.winning_mates([CP(800)])) == 0)

# --- headline_understates ----------------------------------------------------

check("eleven mated replies against one that is not",
      solve.headline_understates(CP(800), 11, 1) is True,
      "8/8/8/4b1p1/5pP1/R3k2P/3p4/5K2 b, the mate in 13")

check("a single mated reply is ordinary",
      solve.headline_understates(CP(800), 1, 5) is False,
      "one losing reply getting mated says nothing about the rest")

check("mated replies must outnumber the others",
      solve.headline_understates(CP(800), 2, 4) is False)

check("a mate in the headline settles it",
      solve.headline_understates(MATE(13), 11, 1) is False,
      "nothing is understated once the headline is itself a mate")

# --- the full-enumeration verdict ------------------------------------------
#
# Since 2.27.0 these call solve.enumeration_verdict() itself. Until then this
# file carried a copy of the branch in run() and tested the copy -- which passes
# whatever the original does, and went on passing while the original printed
# "the win is forced" on a fortress.

def keys(best, pairs, notes=None):
    rows = [(san, score, "", (notes or {}).get(san, "d16")) for san, score in pairs]
    return [k for k, _ in solve.enumeration_verdict(best, rows, 400)]


eleven_of_twelve = [("Rxc3+", CP(842))] + [(f"m{i}", MATE(3 + i))
                                           for i in range(11)]
all_mated = [(f"m{i}", MATE(3 + i)) for i in range(12)]
fortress = [("Kc2", CP(1071)), ("Ka1", CP(1071)), ("Kb2", CP(1090)),
            ("Kc1", CP(1102))]

check("a fortress: every reply decisive in centipawns is not a proof",
      keys(CP(1071), fortress) == ["v_decisive"],
      "the regression: this printed 'the win is forced' until 2.27.0")
check("every reply mated -> the win is proved",
      keys(CP(800), all_mated) == ["v_forced"])
check("a mate headline proves the win by itself",
      keys(MATE(13), eleven_of_twelve) == ["v_forced"])
check("eleven mated, the toughest in centipawns -> not proved, the note fires",
      keys(CP(800), eleven_of_twelve) == ["v_decisive", "v_forced_mates"],
      "v_forced + v_forced_mates before 2.27.0")
check("a reply that holds -> the stronger message",
      keys(CP(800), eleven_of_twelve + [("Kg2", CP(30))]) == ["v_branch_mates"])
check("one mated reply and a holder -> the ordinary verdict",
      keys(CP(800), [("Kg2", CP(30)), ("Kg1", MATE(4))]) == ["v_holds"])
check("an unscored reply -> completeness not proved",
      keys(CP(800), [("Kg2", CP(0)), ("Kg1", MATE(3))],
           notes={"Kg2": solve.t("r_unscored")}) == ["v_incomplete"])
check("v_decisive formats and says what it is",
      "not a proof" in solve.t("v_decisive", n=4, k=4, floor="+10.71"))

# --- the messages themselves format ------------------------------------------

check("v_forced_mates formats",
      "Rxc3+" in solve.t("v_forced_mates", n=11, total=12, san="Rxc3+"))

# --- gap_note on lines that came back out of order --------------------------

try:
    note = solve.gap_note(MATE(-3), CP(-500))
    check("a mated best line over an unmated second is reported, not a crash",
          "out of order" in note)
except TypeError as exc:
    check("a mated best line over an unmated second is reported, not a crash",
          False, f"TypeError: {exc}")

print()
if failures:
    print(f"{len(failures)} failed: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
