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
"""Tests for what the mate ladder is allowed to claim about absence.

    python3 tests/test_ladder.py

The bug these exist to catch: a rung that ran out of budget looks from outside
exactly like a rung that proved there is no mate at that distance. `solve.py`
knows this -- it is the whole reason `probe_shorter` descends instead of
climbing -- and until 2.24.0 the ladder's own report of itself made the mistake
anyway. A run given `--budget 5 --mate-probe 16 --probe-step 3` on
`8/8/8/4k3/8/8/8/R3K3 w` managed one rung and wrote "no mate up to 16" into the
timing table and the shared journal.

These drive the ladder with a scripted engine rather than Stockfish. What is
being tested is a claim about how far the search got, so the test must not
depend on how fast the machine was on the day -- which is exactly the property
a real engine would take away.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "scripts"))

import chess          # noqa: E402
import chess.engine   # noqa: E402

import solve          # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}"
          f"{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


BOARD = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")


class ScriptedEngine:
    """Answers `go mate n` from a table; records every rung it was asked.

    `mates[n]` is the distance the engine claims to see when asked for a mate
    in at most n, or absent for "no mate at that distance". A depth-limited
    call -- the one `_fill_pv` makes to lengthen a truncated line -- comes back
    with a line no longer than the one it was given, so `_fill_pv` keeps the
    original and the test stays about the ladder.
    """

    def __init__(self, mates=None):
        self.mates, self.asked = mates or {}, []

    def _reply(self, board, score):
        move = next(iter(board.legal_moves))
        return {"score": chess.engine.PovScore(score, board.turn),
                "pv": [move]}

    def analyse(self, board, limit, **kwargs):
        if limit.mate is None:                    # _fill_pv's follow-up search
            return self._reply(board, chess.engine.Cp(30))
        self.asked.append(limit.mate)
        found = self.mates.get(limit.mate)
        if found is None:
            return self._reply(board, chess.engine.Cp(30))
        return self._reply(board, chess.engine.Mate(found))


def session(engine, seconds_left):
    """A Session with no Stockfish behind it: the ladder only needs left()."""
    ses = solve.Session.__new__(solve.Session)
    ses.engine = engine
    ses.started = time.time()
    ses.deadline = time.time() + seconds_left
    return ses


# --- probe_mate: how far absence was actually proved -------------------------

eng = ScriptedEngine()
n, line, proved_to = session(eng, 60).probe_mate(BOARD, rungs=5, step=0.3)

check("a ladder that ran out proves absence up to its last rung",
      (n, proved_to) == (None, 5), f"asked {eng.asked}")

eng = ScriptedEngine()
n, line, proved_to = session(eng, 0.0).probe_mate(BOARD, rungs=16, step=3.0)

check("a ladder the budget stopped before rung 1 proves nothing",
      (n, proved_to, eng.asked) == (None, 0, []),
      "the regression: this reported 'no mate up to 16'")

eng = ScriptedEngine({3: 3, 4: 3, 5: 3})
n, line, proved_to = session(eng, 60).probe_mate(BOARD, rungs=5, step=0.3)

check("a hit at rung 3 leaves absence proved only up to 2",
      (n, proved_to, eng.asked) == (3, 2, [1, 2, 3]))

eng = ScriptedEngine({2: 7})            # a longer mate than the rung asked for
n, line, proved_to = session(eng, 60).probe_mate(BOARD, rungs=3, step=0.3)

check("a mate longer than the rung is not what that rung proved",
      (n, proved_to) == (None, 3), "rung 2 answered, but not the question")


# --- probe_shorter: "nothing shorter" is a claim, not a timeout --------------

eng = ScriptedEngine()
n, line, proved = session(eng, 60).probe_shorter(BOARD, m=6, step=3.0)

check("a rung that answered proves nothing shorter exists",
      (n, proved, eng.asked) == (None, True, [5]))

eng = ScriptedEngine()
n, line, proved = session(eng, 0.0).probe_shorter(BOARD, m=6, step=3.0)

check("a rung the budget never reached proves nothing",
      (n, proved, eng.asked) == (None, False, []),
      "the regression: this reported 'nothing shorter than 6'")

eng = ScriptedEngine({5: 5, 4: 4, 3: 1})
n, line, proved = session(eng, 60).probe_shorter(BOARD, m=6, step=3.0)

check("descending to a mate in 1 needs no further rung",
      (n, proved, eng.asked) == (1, True, [5, 4, 3]))


# --- the three-way choice the caller makes from those returns ----------------
#
# Mirrors the branch in solve.run(). Kept here rather than driven end to end
# because the input is "how far the ladder got", which on a real engine is a
# fact about the machine's speed that afternoon.

def outcome(probe_n, proved_to, rungs):
    if probe_n:
        return "probe_found"
    return "probe_none" if proved_to >= rungs else "probe_cut"


check("a full ladder still says 'no mate up to N'",
      outcome(None, 5, 5) == "probe_none")
check("a stopped ladder says how far it got instead",
      outcome(None, 1, 16) == "probe_cut")
check("a hit outranks both",
      outcome(4, 3, 16) == "probe_found")


# --- the messages themselves format ------------------------------------------

check("ladder_cut names the rungs that were never asked",
      "2 to 16" in solve.t("ladder_cut", done=1, first=2, rungs=16))
check("reprobe_cut_note refuses to call the mate the fastest win",
      "fastest win" in solve.t("reprobe_cut_note", m=23, n=22))

# --- the playout: why it stopped ---------------------------------------------

class Shuffler:
    """Knights out and back, so the start position recurs a third time at ply 8."""

    def __init__(self):
        self.i = 0

    def analyse(self, board, limit, **kwargs):
        cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
        move = chess.Move.from_uci(cycle[self.i % 4])
        self.i += 1
        return {"score": chess.engine.PovScore(chess.engine.Cp(900), board.turn),
                "pv": [move]}


res = session(Shuffler(), 60).playout(chess.Board(), plies=60, step=0.01)
notes = solve.playout_notes(res, 60)
check("a playout that reaches a claimable draw says so",
      res["reason"] == "ended" and res["claimable"] and "playout_claimable" in notes,
      f"{res['reason']} after {res['plies']} plies")
check("... and does not claim the budget ran out",
      "playout_cut" not in notes,
      "the regression: the fortress playout was reported as a timeout")

res = session(Shuffler(), 0.0).playout(chess.Board(), plies=60, step=0.01)
check("a playout the budget stops is still reported as cut",
      solve.playout_notes(res, 60)[-1] == "playout_cut")

base = dict(first_reset=None, over=False, claimable=False, reason="done")
check("a run that used up 60 plies with no reset asks for 100, not a verdict",
      "playout_limit" in solve.playout_notes({**base, "plies": 60}, 60))
check("a run that used all 100 plies says the fifty-move rule has spoken",
      "playout_limit_full" in solve.playout_notes({**base, "plies": 100}, 100))
check("a reset settles it: no limit note",
      "playout_limit" not in solve.playout_notes(
          {**base, "first_reset": 53, "plies": 60}, 60))

# --- the main search: a mate found at the stop depth is kept ---------------

class Stream:
    """engine.analysis() played back from a fixed list of info lines."""

    def __init__(self, infos):
        self.infos = infos

    def analysis(self, board, limit, **kwargs):
        infos = self.infos

        class Manager:
            def __enter__(self):
                return iter(infos)

            def __exit__(self, *exc):
                return False
        return Manager()


MATING = chess.Board("r1bq1rk1/pp1n1p1p/5P2/1B3p2/3B3b/PR6/2PQ2PP/3K3R w - - 0 1")
m1, m2 = list(MATING.legal_moves)[:2]
W = chess.WHITE
stream = [
    {"depth": 12, "multipv": 1, "pv": [m1], "score": chess.engine.PovScore(chess.engine.Cp(892), W)},
    {"depth": 12, "multipv": 2, "pv": [m2], "score": chess.engine.PovScore(chess.engine.Cp(212), W)},
    {"depth": 13, "multipv": 1, "pv": [m1], "score": chess.engine.PovScore(chess.engine.Mate(6), W)},
]
lines, reached, _ = session(Stream(stream), 60).search(
    MATING, multipv=2, soft=5, hard=15, min_depth=18, max_depth=30, stable=5)
check("a mate found at the stop depth is reported, not the depth before",
      lines[1].score.pov(W).is_mate() and reached == 13,
      "the regression: +8.92 at depth 12 was returned for a mate in 6")
check("... and the second line keeps its own, earlier depth",
      lines[2].depth == 12)

print()
if failures:
    print(f"{len(failures)} failed: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
