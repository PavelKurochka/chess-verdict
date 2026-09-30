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
"""Tests for the tablebase probe added in 2.31.0.

    python3 tests/test_tablebase.py            # offline, instant
    python3 tests/test_tablebase.py --live     # plus one real query

The offline part feeds `tablebase_query()` stand-ins for urlopen, so the split
between "the allowlist refuses the host" and "the network failed today" is
checked without a network -- that split decides whether the user is sent to
their settings. The answers used for `tablebase_report()` are real ones,
recorded from tablebase.lichess.ovh on 2026-09-30.

`--live` asks the service about K+B+N vs K. A sandbox whose allowlist does not
include the host is not a failure: the test says SKIP and exits 0, because the
setting belongs to the user and the skill works without it.
"""

import io
import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "scripts"))

import chess  # noqa: E402

import solve  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}"
          f"{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


def raising(exc):
    def opener(url, timeout=None):
        raise exc
    return opener


def http_error(code, body):
    return urllib.error.HTTPError("https://x", code, "err", {},
                                  io.BytesIO(body.encode()))


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def answering(text):
    return lambda url, timeout=None: Resp(text.encode())


FEN = "8/8/8/8/8/2k5/8/KBN5 w - - 0 1"

# --- classification ----------------------------------------------------------

kind, _ = solve.tablebase_query(FEN, opener=raising(urllib.error.URLError(
    OSError("Tunnel connection failed: 403 Forbidden"))))
check("a refused CONNECT is the allowlist", kind == "blocked", kind)

kind, _ = solve.tablebase_query(FEN, opener=raising(urllib.error.URLError(
    OSError("Tunnel connection failed: 403 host_not_allowed"))))
check("host_not_allowed in the tunnel error is the allowlist",
      kind == "blocked", kind)

kind, _ = solve.tablebase_query(FEN, opener=raising(
    http_error(403, '{"error":"host_not_allowed"}')))
check("a 403 naming the policy is the allowlist", kind == "blocked", kind)

kind, _ = solve.tablebase_query(FEN, opener=raising(http_error(407, "")))
check("a 407 is the proxy", kind == "blocked", kind)

kind, why = solve.tablebase_query(FEN, opener=raising(
    http_error(429, "Too many requests")))
check("a 429 from Lichess is a failure, not a setting",
      kind == "failed" and "429" in why, f"{kind} {why}")

kind, _ = solve.tablebase_query(FEN, opener=raising(TimeoutError("timed out")))
check("a timeout is a failure", kind == "failed", kind)

kind, _ = solve.tablebase_query(FEN, opener=raising(urllib.error.URLError(
    OSError("[Errno -3] Temporary failure in name resolution"))))
check("a DNS error is a failure", kind == "failed", kind)

kind, _ = solve.tablebase_query(FEN, opener=answering("<html>oops</html>"))
check("an answer that is not JSON is a failure", kind == "failed", kind)

seen = []
solve.tablebase_query(FEN, opener=lambda url, timeout=None:
                      (seen.append(url), Resp(b"{}"))[1])
check("spaces in the FEN become underscores",
      seen and seen[0].endswith("8/8/8/8/8/2k5/8/KBN5_w_-_-_0_1"),
      seen[0] if seen else "")

# --- report ------------------------------------------------------------------

KBN = {"category": "win", "dtz": 59, "dtm": 59, "moves": [
    {"uci": "c1e2", "san": "Ne2+", "category": "loss", "dtz": -58, "dtm": -58},
    {"uci": "b1a2", "san": "Ba2", "category": "draw", "dtz": 0, "dtm": 0}]}
lines, final = solve.tablebase_report(chess.Board(FEN), KBN)
text = "\n".join(lines)
check("K+B+N is reported won", "White to move -- won" in text, lines[0])
check("DTM 59 plies is a mate in 30", "mate in 30" in lines[1], lines[1])
check("a move whose reply loses is a win for the mover, same distance",
      "Ne2+ (wins, mate in 30)" in text, lines[-1])
check("a drawn move stays drawn", "Ba2 (draws)" in text, lines[-1])
check("the closing line carries the verdict", "won" in final, final)

CURSED = {"category": "cursed-win", "dtz": 59, "dtm": 59, "moves": [
    {"uci": "c1e2", "san": "Ne2+", "category": "blessed-loss",
     "dtz": -58, "dtm": -58}]}
board = chess.Board("8/8/8/8/8/2k5/8/KBN5 w - - 45 1")
lines, final = solve.tablebase_report(board, CURSED)
text = "\n".join(lines)
check("a cursed win is not called a win outright",
      "drawn by the fifty-move rule" in lines[0], lines[0])
check("the clock is named when it decides", "(45)" in text, lines[1])
check("a blessed loss after the move is a cursed win for the mover",
      "Ne2+ (cursed win" in text, lines[-1])

LOST = {"category": "loss", "dtz": -30, "dtm": -30, "moves": [
    {"uci": "a1b1", "san": "Kb1", "category": "win", "dtz": 29, "dtm": 29}]}
lines, _ = solve.tablebase_report(chess.Board("8/8/8/8/8/2k5/8/K7 b - - 0 1"),
                                  LOST)
check("a loss counts the mate against the side to move",
      "Black to move -- lost" in lines[0] and "mated in 15" in lines[1],
      " | ".join(lines))

lines, _ = solve.tablebase_report(chess.Board(FEN),
                                  {"category": None, "moves": []})
check("an empty answer says so rather than guessing",
      "not answered" in lines[0], lines[0])

# --- live --------------------------------------------------------------------

if "--live" in sys.argv:
    kind, data = solve.tablebase_query(FEN)
    if kind == "blocked":
        print(f"SKIP  live query: the allowlist refuses "
              f"{solve.TABLEBASE_HOST} ({data}) -- see README, "
              f"'Exact endgames'")
    elif kind == "failed":
        print(f"SKIP  live query failed today: {data}")
    else:
        check("live: K+B+N vs K is a win, DTM 59",
              data.get("category") == "win" and data.get("dtm") == 59,
              f"{data.get('category')} dtm={data.get('dtm')}")

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all passed'}")
sys.exit(1 if failures else 0)
