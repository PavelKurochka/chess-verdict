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

# --- the playout since 2.35.0: its own time, its moves, the tablebase anchor --

check("the chat's playout fits its reserve: 100 plies at 0.8 s",
      solve.playout_reserve(100, 0.8, False) >= 100 * 0.8 + 5,
      "--budget 60 cut it at ply 62")
check("... and a possible tablebase query adds its timeout",
      solve.playout_reserve(100, 0.8, True)
      == solve.playout_reserve(100, 0.8, False) + solve.TABLEBASE_TIMEOUT)
check("the cut note no longer sends the reader to --budget",
      "does not help" in solve.t("playout_cut", plies=62, asked=100))

ses = session(Shuffler(), 0.0)
ses.reserve(solve.playout_reserve(6, 0.01, False))
res = ses.playout(chess.Board(), plies=6, step=0.01)    # before the repetition
check("a reserve lets the playout run after the budget is spent",
      res["reason"] == "done" and res["plies"] == 6,
      f"{res['reason']} after {res['plies']} plies")
ses = session(Shuffler(), 60)
ses.reserve(10)
check("a reserve is added to a deadline still ahead, not to now",
      65 < ses.left() <= 70, f"{ses.left():.1f} s left")


class Script:
    """Plays fixed moves; every evaluation is `cp` from White's side."""

    def __init__(self, ucis, cp=600):
        self.ucis, self.cp, self.i = list(ucis), cp, 0

    def analyse(self, board, limit, **kwargs):
        move = chess.Move.from_uci(self.ucis[self.i])
        self.i += 1
        return {"score": chess.engine.PovScore(chess.engine.Cp(self.cp),
                                               chess.WHITE),
                "pv": [move]}


class Tablebase:
    """Stands in for tablebase_query; records every position it was asked."""

    def __init__(self, kind, data):
        self.answer, self.asked = (kind, data), []

    def __call__(self, fen):
        self.asked.append(fen)
        return self.answer


EIGHT = chess.Board("k7/pp6/8/8/8/8/PP6/K1R4r w - - 0 1")   # Rxh1 leaves seven
MOVES = ["c1h1", "a7a6", "h1h2", "a6a5"]


def anchored(kind, data, cp=600, board=EIGHT):
    tb = Tablebase(kind, data)
    res = session(Script(MOVES, cp), 60).playout(board, plies=4, step=0.01,
                                                  tablebase=tb)
    return res, tb


res, tb = anchored("ok", {"category": "loss"})        # Black to move, lost
notes = solve.playout_notes(res, 4)
report = "\n".join(solve.playout_report(res, 4, EIGHT, 0.01, 10.1))
check("the playout stops at the first seven-man position the tablebase answers",
      res["reason"] == "tablebase" and res["anchor"]["ply"] == 1
      and res["anchor"]["men"] == 7 and len(tb.asked) == 1,
      f"{res['reason']}, asked {len(tb.asked)}")
check("... with the category turned round to the side that played out",
      res["anchor"]["category"] == "win" and "for White the position is won"
      in report)
check("... and a won anchor carries no warning",
      "playout_anchor" in notes and "playout_anchor_lost" not in notes
      and "playout_anchor_promo" not in notes, str(notes))
check("the report prints the moves and the clock resets",
      "Moves: 1. Rxh1" in report and "1 Rxh1 (rook)" in report)
check("the header states the time set aside",
      "10 s set aside on top of --budget" in report)

res, _ = anchored("ok", {"category": "draw"})
check("a drawn anchor from a decisive start says the conversion failed",
      "playout_anchor_lost" in solve.playout_notes(res, 4))
res, _ = anchored("ok", {"category": "draw"}, cp=20)
check("... but not from an equal start, where there was nothing to convert",
      "playout_anchor_lost" not in solve.playout_notes(res, 4))
res, _ = anchored("ok", {"category": "win"}, cp=-1100)  # Black to move wins
check("the side judged is the one the evaluation favoured, as in a fortress",
      "playout_anchor_lost" not in solve.playout_notes(res, 4),
      "White to move at the start, Black a rook up")

res, tb = anchored("blocked", "HTTP 403")
notes = solve.playout_notes(res, 4)
check("a refused tablebase is asked once and the playout goes on",
      len(tb.asked) == 1 and res["reason"] == "done" and res["plies"] == 4,
      f"asked {len(tb.asked)}, {res['reason']} after {res['plies']}")
check("... and the report says so",
      "playout_tb_none" in notes and "allowlist refuses tablebase.lichess.ovh" in "\n".join(
          solve.playout_report(res, 4, EIGHT, 0.01, 10.1)))

SEVEN = chess.Board("k7/pp6/8/8/8/8/PP6/K6R b - - 0 1")
tb = Tablebase("ok", {"category": "win"})
res = session(Script(["a7a6", "h1h2"]), 60).playout(SEVEN, plies=2, step=0.01,
                                                     tablebase=tb)
check("from seven men or fewer the playout does not ask again",
      tb.asked == [] and res["anchor"] is None and res["plies"] == 2)

anchor = {"ply": 40, "men": 7, "fen": EIGHT.fen(), "category": "win"}
promo = dict(base, first_reset=5, plies=40, reason="tablebase", anchor=anchor,
             first=chess.engine.Cp(600))
check("a promotion before the anchor is flagged: it confirms the queen only",
      "playout_anchor_promo" in solve.playout_notes({**promo, "promoted": 30}, 60))
check("... and one after it is not",
      "playout_anchor_promo" not in solve.playout_notes(
          {**promo, "promoted": None}, 60))

LINE = [chess.Move.from_uci(u) for u in
        ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5c6", "d7c6")]
check("movetext numbers the moves",
      solve.playout_movetext(chess.Board(), LINE, []) ==
      "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Bxc6 dxc6")
after_e4 = chess.Board()
after_e4.push(LINE[0])
check("... from Black's move too",
      solve.playout_movetext(after_e4, LINE[1:3], []) == "1... e5 2. Nf3")
check("... with an evaluation every N plies, from the playing side",
      solve.playout_movetext(chess.Board(), LINE[:3],
                             [chess.engine.Cp(10), chess.engine.Cp(20),
                              chess.engine.Mate(3)], every=2)
      == "1. e4 e5 {#3} 2. Nf3")
check("the clock resets name what was taken",
      solve.playout_resets(chess.Board(), LINE) ==
      ["1 e4", "2 e5", "6 a6", "7 Bxc6 (knight)", "8 dxc6 (bishop)"])

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


# --- probe_deep: one direct mate query after a huge score (issue #3) ----------
#
# Stockfish 19 often ends the main search on the queen sacrifice in
# tests/positions.tsv at +62 to +92 with no mate, while `go mate 25` finds the
# mate in 17 every time. The query must report what it was asked -- a mate no
# longer than n -- and nothing when the answer is anything else.

eng = ScriptedEngine({30: 17})
n, line = session(eng, 60).probe_deep(BOARD, 30, 3.0)
check("a direct mate query returns the mate it found",
      n == 17 and line is not None and line.proved and eng.asked == [30])

eng = ScriptedEngine()
n, line = session(eng, 60).probe_deep(BOARD, 30, 3.0)
check("no mate in the answer -> nothing, not a claim of absence",
      (n, line) == (None, None))

eng = ScriptedEngine({30: 34})          # a mate longer than was asked for
n, line = session(eng, 60).probe_deep(BOARD, 30, 3.0)
check("a mate longer than asked for is not what the query proved",
      (n, line) == (None, None))


# --- _fill_pv has a clock ------------------------------------------------------
#
# Lengthening a mate in 17 is a search to depth 36; until 2.30.0 it had no time
# limit. The limit must be there, and must not outrun the budget.

class LimitRecorder(ScriptedEngine):
    def analyse(self, board, limit, **kwargs):
        self.fill_limit = limit
        return super().analyse(board, limit, **kwargs)


rec = LimitRecorder()
session(rec, 60)._fill_pv(BOARD, 17, solve.Line(None, None, []))
check("lengthening a long mate line is capped in time, not only in depth",
      rec.fill_limit.depth == 36 and rec.fill_limit.time == solve.FILL_PV_TIME,
      f"limit {rec.fill_limit}")

rec = LimitRecorder()
session(rec, 0.5)._fill_pv(BOARD, 17, solve.Line(None, None, []))
check("... and never past what is left of the budget",
      rec.fill_limit.time <= 0.5, f"limit {rec.fill_limit}")


# --- a dead engine is an error, not a timeout ---------------------------------
#
# EngineTerminatedError is a subclass of EngineError, so every `except
# EngineError` in Session swallowed it. On a position Stockfish 19 refuses, the
# ladder then reported "the budget ran out" one second into thirty and advised
# a bigger --budget. Each method must let it through to run(), which says what
# happened.

class DeadEngine:
    def analyse(self, *args, **kwargs):
        raise chess.engine.EngineTerminatedError("engine process died unexpectedly")

    def quit(self):
        raise chess.engine.EngineTerminatedError("engine event loop dead")


def propagates(call):
    try:
        call(session(DeadEngine(), 60))
    except chess.engine.EngineTerminatedError:
        return True
    return False


for name, call in [
        ("probe_deep", lambda s: s.probe_deep(BOARD, 30, 0.1)),
        ("probe_mate", lambda s: s.probe_mate(BOARD, rungs=5, step=0.3)),
        ("probe_shorter", lambda s: s.probe_shorter(BOARD, m=6, step=0.3)),
        ("_fill_pv", lambda s: s._fill_pv(BOARD, 3, solve.Line(None, None, []))),
        ("playout", lambda s: s.playout(BOARD, plies=4, step=0.1)),
        ("evaluate_at_clock", lambda s: s.evaluate_at_clock(BOARD, seconds=0.1)),
]:
    check(f"{name} lets a dead engine through instead of reading it as a stop",
          propagates(call))

try:
    session(DeadEngine(), 60).close()
    closed = True
except chess.engine.EngineError:
    closed = False
check("close() on a dead engine does not raise a second traceback", closed)

print()
if failures:
    print(f"{len(failures)} failed: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
