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
"""Offline tests for the recognizer: render a FEN, read it back, compare.

    python3 tests/test_reader.py            # fixed cases, about 5 s
    python3 tests/test_reader.py --sweep    # the 2.25.0 held-out figure, ~1 min

The fixture carries its own answer: every image is rendered from the FEN it is
checked against, so no downloaded dataset is needed. That is the point. The
only other thing that touches the reader, scripts/reader_eval.py, needs hosts
the container blocks, which left the recognizer with no automated cover at all
until 2.25.0.

Only one piece set and one rasteriser (python-chess's own set, rsvg-convert).
A green run says the pipeline works on that; it says nothing about the piece
sets in real books.
"""

import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, "scripts")
sys.path.insert(0, SCRIPTS)

import chess        # noqa: E402
import chess.svg    # noqa: E402

if not shutil.which("rsvg-convert"):
    print("SKIPPED: rsvg-convert is not installed (apt-get install -y librsvg2-bin)")
    sys.exit(0)
try:
    import onnxruntime  # noqa: F401
    import img2fen      # noqa: E402
except ImportError as exc:
    print(f"SKIPPED: the recognizer's runtime is missing ({exc})")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="cv-reader-")
failures = []


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}"
          f"{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


def render(placement, width, colors=None, name="board"):
    svg = chess.svg.board(chess.Board(placement + " w - - 0 1"), size=520,
                          coordinates=True, colors=colors or {})
    path = os.path.join(TMP, f"{name}_{width}.png")
    subprocess.run(["rsvg-convert", "-w", str(width), "-o", path],
                   input=svg.encode(), check=True)
    return path


def read_cli(path, *extra):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "img2fen.py"),
                           path, *extra], capture_output=True, text=True).stdout


# --- the box one square off on both axes ------------------------------------

SILENT = "7Q/8/8/8/6p1/5pPb/5PpP/2k3K1"
r = img2fen.recognize(render(SILENT, 150, name="silent"))
check("the 150 px render that was silently misread now reads right",
      r is not None and r["placement"] == SILENT,
      f"read {r['placement'] if r else None}")
check("... and says the box was moved", bool(r and r.get("shifted")))

NORMAL = "5rrk/1p1n3p/4pp1Q/3pP3/p2N3P/P2P2P1/4qPK1/1R5R"
r = img2fen.recognize(render(NORMAL, 520, name="normal"))
check("a box that fits the image is left alone",
      r is not None and r["placement"] == NORMAL and not r.get("shifted"))

# --- the side to move ---------------------------------------------------------

out = read_cli(os.path.join(TMP, "normal_520.png"))
check("no turn given: two FENs and no bare FEN line",
      "FEN if White to move:" in out and "FEN if Black to move:" in out
      and "\nFEN: " not in out and "NOT READ" in out)

out = read_cli(os.path.join(TMP, "normal_520.png"), "b")
check("an explicit turn gives one FEN with that turn",
      f"FEN: {NORMAL} b " in out and "FEN if" not in out)

CHECK = "4k3/8/8/8/8/8/4r3/4K3"          # White's king on e1 is in check
out = read_cli(render(CHECK, 520, name="check"))
check("a king in check settles the turn, and it says why",
      f"FEN: {CHECK} w " in out and "is in check" in out, out.strip()[-120:])

out = read_cli(os.path.join(TMP, "normal_520.png"), "--view", "black")
check("--view black still defaults to Black and says so",
      " b " in out and "from the side the diagram is drawn from" in out)


# --- the held-out sweep behind the 2.25.0 figures -----------------------------

def sweep():
    random.seed(20260921)
    positions = []
    while len(positions) < 30:
        b = chess.Board()
        for _ in range(random.randint(10, 90)):
            if b.is_game_over():
                break
            b.push(random.choice(list(b.legal_moves)))
        if not b.is_game_over():
            positions.append(b.board_fen())
    themes = {"brown": {},
              "blue": {"square light": "#dee3e6", "square dark": "#8ca2ad"},
              "green": {"square light": "#eeeed2", "square dark": "#769656"}}
    tally = dict(correct=0, refused=0, flagged=0, silent=0)
    for i, pl in enumerate(positions):
        for th, col in themes.items():
            for w in (140, 160, 180, 200, 230, 260, 300, 360, 440, 560):
                res = img2fen.recognize(render(pl, w, col, f"s{i}{th}"))
                if res is None or res["min_confidence"] < img2fen.MIN_CONFIDENCE:
                    tally["refused"] += 1
                elif res["placement"] == pl:
                    tally["correct"] += 1
                else:
                    try:
                        legal = chess.Board(res["placement"] + " w - - 0 1"
                                            ).status() == chess.STATUS_VALID
                    except ValueError:
                        legal = False
                    tally["silent" if legal and res["plausible"] else "flagged"] += 1
    print(f"\nheld-out sweep, 900 renders: {tally}")
    check("the sweep has no silent misread", tally["silent"] == 0)


if "--sweep" in sys.argv:
    sweep()

shutil.rmtree(TMP, ignore_errors=True)
print()
if failures:
    print(f"{len(failures)} failed: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
