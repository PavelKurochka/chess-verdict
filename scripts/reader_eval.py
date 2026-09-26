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
"""Measure the diagram reader across piece sets.

Builds the stand and scores it: every position rendered in every lichess
piece set, so that between two renderings of the same position exactly one
thing varies. That is the axis the reader used to fail on, and the axis no
benchmark of a single piece set can see.

    python3 reader_eval.py --render        # fetch the sets, draw the stand
    python3 reader_eval.py                 # score the reader on it

Three outcomes, and the middle one is the point:

  correct   the placement matches and the reader stood behind it
  WRONG     the placement does not match and the reader stood behind it
            anyway -- a silent wrong answer
  refused   no reading, or a reading marked as untrusted

A refusal is not a success, but it is not the same failure. It costs a
round trip; a silent wrong answer reaches the user as a verdict about a
position that was never on the board. Folding the two together hides the
difference the whole measurement exists to show. A reading that was marked
untrusted counts as refused even when it happens to be right: the reader
disclaimed it, so it cannot be credited with it.

The stand needs the lichess piece sets, fetched from
raw.githubusercontent.com. `data.4tu.nl`, `kaggle.com` and
`storage.googleapis.com` are blocked by the container's egress policy, so
the photographic sets (ChessReD, the koryakin "Chess Positions" set) cannot
be pulled here. What that costs is stated under "What this does not
measure" below; it is not a small caveat and should not be read as one.
"""

import argparse
import json
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import img2fen                                                  # noqa: E402

PIECE_URL = ("https://raw.githubusercontent.com/lichess-org/lila/master/"
             "public/piece/{set_}/{piece}.svg")

SETS = ("alpha cardinal cburnett celtic chess7 chessnut companion dubrovny "
        "fantasy fresca governor icpieces kosal leipzig maestro merida "
        "pirouetti spatial staunty tatiana").split()

PIECE_FILE = {
    "K": "wK", "Q": "wQ", "R": "wR", "B": "wB", "N": "wN", "P": "wP",
    "k": "bK", "q": "bQ", "r": "bR", "b": "bB", "n": "bN", "p": "bP",
}

LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
SIZE = 512
SQ = SIZE // 8


def expand(placement):
    rows = []
    for rank in placement.split("/"):
        row = ""
        for ch in rank:
            row += "." * int(ch) if ch.isdigit() else ch
        rows.append(row)
    return rows


def fetch_pieces(root):
    for set_ in SETS:
        d = root / set_
        d.mkdir(parents=True, exist_ok=True)
        for piece in PIECE_FILE.values():
            svg = d / f"{piece}.svg"
            if svg.exists():
                continue
            url = PIECE_URL.format(set_=set_, piece=piece)
            with urllib.request.urlopen(url, timeout=30) as r:
                svg.write_bytes(r.read())
    return SETS


def rasterise_set(piece_dir, cache_dir):
    """Each glyph to its own PNG at square size.

    Rasterised one at a time and composited afterwards, which looks like a
    detour and is not. Embedding twelve `<svg>` glyphs into one board
    document is the obvious way and it is wrong: celtic, fantasy, kosal and
    spatial carry a `<style>` block with short class names like `.st15`, and
    CSS in SVG is document-wide however deeply the element is nested. Put
    together, the black king's rules overwrite the white king's and the
    board renders in one colour.

    That version of this script produced a stand on which four sets scored
    zero out of ten for reasons that had nothing to do with any recognizer.
    The numbers looked plausible and were entirely false -- a fault in the
    measuring instrument, where the output is indistinguishable from a
    finding. `--self-check` below exists because of it.
    """
    from PIL import Image

    cache_dir.mkdir(parents=True, exist_ok=True)
    glyphs = {}
    for ch, name in PIECE_FILE.items():
        png = cache_dir / f"{name}.png"
        if not png.exists():
            proc = subprocess.run(
                ["rsvg-convert", "-w", str(SQ), "-h", str(SQ),
                 "-o", str(png), str(Path(piece_dir) / f"{name}.svg")],
                capture_output=True)
            if proc.returncode != 0:
                raise SystemExit(f"rsvg-convert failed on {name}: "
                                 f"{proc.stderr.decode()[:200]}")
        glyphs[ch] = Image.open(png).convert("RGBA")
    return glyphs


def render(placement, glyphs, out_png):
    from PIL import Image

    img = Image.new("RGB", (SIZE, SIZE))
    for r in range(8):
        for f in range(8):
            colour = LIGHT if (r + f) % 2 == 0 else DARK
            img.paste(Image.new("RGB", (SQ, SQ), colour), (f * SQ, r * SQ))
    for r, row in enumerate(expand(placement)):
        for f, ch in enumerate(row):
            if ch != ".":
                img.paste(glyphs[ch], (f * SQ, r * SQ), glyphs[ch])
    img.save(out_png)


def self_check(glyphs, set_):
    """Do White's and Black's glyphs actually differ?

    The cheapest possible guard against the CSS collision described above,
    and enough: a set whose two rooks rasterise to the same pixels is not a
    piece set, it is a bug.
    """
    import numpy as np
    from PIL import Image

    white = np.asarray(Image.alpha_composite(
        Image.new("RGBA", glyphs["R"].size, (255, 255, 255, 255)), glyphs["R"]))
    black = np.asarray(Image.alpha_composite(
        Image.new("RGBA", glyphs["r"].size, (255, 255, 255, 255)), glyphs["r"]))
    if np.array_equal(white, black):
        raise SystemExit(f"stand is broken: in {set_} the white and black "
                         f"rooks rasterise identically")


def positions(path, limit):
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.startswith("#") and "\t" in line:
            out.append(line.split("\t")[0].split()[0])
    return out[:limit]


def build(root, tsv, limit):
    pieces = root / "pieces"
    fetch_pieces(pieces)
    diagrams = root / "diagrams"
    diagrams.mkdir(parents=True, exist_ok=True)
    truth = []
    for set_ in SETS:
        glyphs = rasterise_set(pieces / set_, root / "glyphs" / set_)
        self_check(glyphs, set_)
        for i, placement in enumerate(positions(tsv, limit)):
            png = diagrams / f"{set_}__{i}.png"
            render(placement, glyphs, png)
            truth.append(f"{png.name}\t{set_}\t{placement}")
    (root / "truth.tsv").write_text("\n".join(truth) + "\n")
    print(f"{len(SETS)} sets x {limit} positions = {len(truth)} diagrams "
          f"in {diagrams}")


def read_one(png, gate):
    result = img2fen.recognize(str(png))
    if result is None:
        return None
    if result["min_confidence"] < gate:
        return None
    return result["placement"]


def score(root, gate):
    truth_file = root / "truth.tsv"
    if not truth_file.exists():
        raise SystemExit(f"no stand at {root}; run with --render first")
    rows = [l.split("\t") for l in truth_file.read_text().splitlines() if l.strip()]
    per_set = defaultdict(lambda: {"correct": 0, "wrong": 0, "refused": 0})
    totals = {"correct": 0, "wrong": 0, "refused": 0}
    silent = []

    for name, set_, truth in rows:
        read = read_one(root / "diagrams" / name, gate)
        if read is None:
            outcome = "refused"
        elif read == truth:
            outcome = "correct"
        else:
            outcome = "wrong"
            silent.append([name, truth, read])
        per_set[set_][outcome] += 1
        totals[outcome] += 1

    print(f"{'set':<12} {'correct':>8} {'SILENT WRONG':>13} {'refused':>8}")
    for s in sorted(per_set):
        c = per_set[s]
        print(f"{s:<12} {c['correct']:>8} {c['wrong']:>13} {c['refused']:>8}")
    print(f"{'TOTAL':<12} {totals['correct']:>8} {totals['wrong']:>13} "
          f"{totals['refused']:>8}")
    (root / "result.json").write_text(json.dumps(
        {"gate": gate, "totals": totals, "per_set": dict(per_set),
         "silent": silent[:40]}, indent=2))
    return totals


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", default="/tmp/reader-eval",
                   help="where the stand lives (default /tmp/reader-eval)")
    p.add_argument("--positions",
                   default=str(Path(__file__).resolve().parent.parent
                               / "tests" / "positions.tsv"))
    p.add_argument("--limit", type=int, default=10,
                   help="positions per piece set (default 10)")
    p.add_argument("--render", action="store_true",
                   help="fetch the piece sets and draw the stand, then stop")
    p.add_argument("--confidence", type=float, default=img2fen.MIN_CONFIDENCE,
                   help="the gate to score at")
    args = p.parse_args()

    root = Path(args.root)
    if args.render:
        build(root, args.positions, args.limit)
        return 0
    score(root, args.confidence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
