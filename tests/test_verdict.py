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

Since 2.35.2 they also cover who the reply list belongs to and what it may call
the toughest defence. With the losing side to move -- after a `--line` that
ends on the defender's turn, as `references/technique.md` asks -- the list is
the winner's replies, and the block printed "the advantage is not decisive.
Toughest defence -- Rxa4" for White's winning move. And two defences 0.03
apart in chances were printed as one "toughest", which the answer repeated.
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

two_unproved = eleven_of_twelve[:1] + [("Kg2", CP(905))] + eleven_of_twelve[1:]
fields = dict(solve.enumeration_verdict(
    CP(800), [(san, score, "", "d16") for san, score in two_unproved], 400))
check("the NOTE lists every reply scored in centipawns, not one 'toughest'",
      fields.get("v_forced_mates", {}).get("others") == "Rxc3+, Kg2",
      repr(fields.get("v_forced_mates")))

# --- the messages themselves format ------------------------------------------

check("v_forced_mates formats",
      "Rxc3+ is scored" in solve.t("v_forced_mates", n=11, total=12,
                                   others="Rxc3+", verb="is"))

# --- losing: which side the headline condemns -------------------------------

check("-40 for the side to move is losing", solve.losing(CP(-4002), 400))
check("a mate against the side to move is losing", solve.losing(MATE(-3), 400))
check("-3 is not losing at --win 400", not solve.losing(CP(-300), 400))
check("a winning score is not losing", not solve.losing(CP(4002), 400))
check("a mate for the side to move is not losing", not solve.losing(MATE(3), 400))

# --- toughest: one reply, or the ones the engine cannot separate ------------

live = [("Bd5", CP(533)), ("Kd5", CP(494)), ("Kf6", CP(700))]
check("0.03 apart in chances is a tie, listed lowest first",
      [san for san, _ in solve.toughest(live)] == ["Kd5", "Bd5"],
      "after 1.Rf1+ Ke5 on 8/8/2b2kp1/p6p/P6P/3K2P1/8/4R3 w: the answer "
      "called Kd5 the toughest by evaluation")
check("a gap past GAP_CHANCES leaves one toughest reply",
      [san for san, _ in solve.toughest([("a", CP(200)), ("b", CP(100))])]
      == ["b"])
check("mates tie only at the same distance; the longest is the toughest",
      [san for san, _ in solve.toughest(
          [("a", MATE(5)), ("b", MATE(7)), ("c", MATE(7))])] == ["b", "c"])
check("a mate is not noise beside a centipawn score, however large",
      [san for san, _ in solve.toughest([("a", MATE(9)), ("b", CP(2000))])]
      == ["b"])
check("the tie words say why there is no single toughest",
      "within search noise" in solve.tough_words(solve.toughest(live)))
check("one reply is named plainly",
      solve.tough_words([("g5", CP(725))]) == "g5 (+7.25)")


# --- the sampled defences ----------------------------------------------------

def sampled(best, replies, mover=chess.WHITE, rest=11):
    out = solve.sampled_verdict(best, replies, 400, rest, mover)
    return out, " ".join(solve.t(k, **f) for k, f in out)


out, text = sampled(CP(-4002), [("Rxa4", CP(-3635)), ("Rd4", CP(-586)),
                                ("Rf4", CP(-532))], mover=chess.BLACK, rest=16)
check("losing side to move -> the winner is named",
      [k for k, _ in out] == ["v_losing"] and "White is winning, not Black"
      in text, text)
check("losing side to move -> the list is the winner's, not defences",
      "White's strongest reply -- Rxa4 (-36.35)" in text
      and "Toughest defence" not in text and "not decisive" not in text,
      "the regression: 'not decisive. Toughest defence -- Rxa4' until 2.35.2")
check("losing side to move -> the rest are rated for the winner",
      "remaining 16 replies were rated no better for White" in text)
_, text = sampled(CP(-4002), [("axb5+", CP(-6917)), ("Bxa4", CP(-6890))],
                  mover=chess.BLACK)
check("losing side to move, two strongest replies in noise -> no single one",
      "No single strongest reply for White" in text, text)
_, text = sampled(MATE(-4), [("Qg7#", MATE(0)), ("Qh8+", MATE(-2))])
check("a mate against White names Black as winning",
      "Black is winning, not White" in text, text)

out, text = sampled(CP(628), live)
check("winning side to move, two defences in noise -> no single toughest",
      [k for k, _ in out] == ["v_tail"]
      and "No single toughest defence -- Kd5 (+4.94), Bd5 (+5.33)" in text
      and "Kf6" not in text, text)
check("the advantage still survives the lowest of them",
      "survives the best defence" in text)
_, text = sampled(CP(800), [("Kh8", CP(900)), ("Kf8", CP(2000))])
check("winning side to move, a clear gap -> one toughest defence",
      "Toughest defence -- Kh8 (+9.00)." in text, text)
_, text = sampled(CP(300), [("Kh8", CP(250)), ("Kf8", CP(900))])
check("an edge short of --win is still 'not decisive', as before",
      "the advantage is not decisive. Toughest defence -- Kh8" in text, text)
out, _ = sampled(CP(800), [("a", MATE(3)), ("b", MATE(4)), ("c", MATE(5)),
                           ("d", CP(900))])
check("most sampled defences mated -> the NOTE still follows",
      [k for k, _ in out] == ["v_tail", "v_tail_mates"])

# --- the full list with the losing side to move -----------------------------

after_ke7 = [("Rxa4", CP(-1626)), ("Rc1", CP(-508)), ("Kf8", CP(0)),
             ("Rc2", CP(888))]


def full(best, pairs, mover, notes=None):
    rows = [(san, score, "", (notes or {}).get(san, "d16"))
            for san, score in pairs]
    out = solve.enumeration_verdict(best, rows, 400, mover=mover)
    return out, " ".join(solve.t(k, **f) for k, f in out)


out, text = full(CP(-1927), after_ke7, chess.BLACK)
check("full list, losing side to move -> the winner, not 'replies hold'",
      [k for k, _ in out] == ["v_losing"] and "White is winning" in text
      and "Rxa4 (-16.26)" in text and "remaining" not in text, text)
out, _ = full(CP(-1927), after_ke7, chess.BLACK,
              notes={"Rc2": solve.t("r_unscored")})
check("full list, losing, an unscored reply -> both lines",
      [k for k, _ in out] == ["v_incomplete", "v_losing"])

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
