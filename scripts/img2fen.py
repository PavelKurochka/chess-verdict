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
"""Recognize a chess diagram into a FEN.

The reader finds the board itself -- gradient profiles across the image,
arithmetic sequences of peaks for the grid lines, checkerboard correlation
to arbitrate between candidates -- so a frame, a caption, a whole page
around the board are not a problem and there is no ladder of crops.

What is done here for speed:
  * the model loads once, not again for every attempt;
  * all 64 squares are classified in one call;
  * no temporary image files are written.

What this prints is a reading, never a verdict. Legality is reported as a
property of the position, the per-side material counts come from solve.py,
and the visual check comes from compare.py. A confident reading of an
illegal position is returned as exactly that.
"""

import time

_STARTED = time.time()

import argparse
import os
import sys

try:
    import chess
except ImportError as exc:
    # A missing python-chess used to end in a bare ModuleNotFoundError. The
    # setup line can fail for reasons that have nothing to do with the network
    # -- on images whose Debian setuptools rejects legacy builds it dies with
    # `AttributeError: install_layout` -- so the message names the fix.
    sys.exit("python-chess is not installed ({exc}). Install it with:\n"
             "  pip install chess --break-system-packages --use-pep517 -q\n"
             "--use-pep517 is not optional decoration: python-chess 1.11 ships "
             "as source only, and without it some images fail to build it. "
             "Nothing was analysed.".format(exc=exc))
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "vendor", "fenshot"))

from solve import FATAL_STATUS, banner, status_words            # noqa: E402
from fenshot_detect import (                                    # noqa: E402
    Gray, checkerboard_score, find_chessboard_corners, snap_corners,
)
from fenshot_tiles import (                                     # noqa: E402
    CONFIDENCE_FLOOR, extract_tiles, flip_placement, infer_castling,
    probs_to_placement,
)

#: Engines the reader can be run with. Only one for now, and the flag
#: exists so that adding a second does not change the command line of the
#: first. A template bank is the intended second.
ENGINES = ("fenshot",)

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "vendor", "fenshot", "chess-tiles-v2.onnx")

#: The detector wants a moderate resolution -- it is looking for grid lines,
#: not for detail -- and the upstream goldens were made at this cap.
MAX_DETECT_DIM = 1600

#: A page can hold more than one board-like region. When a pass reads as
#: nonsense, that region is flattened and the scan repeats.
MAX_SCAN_PASSES = 3

EMPTY_PLACEMENT = "8/8/8/8/8/8/8/8"

# The classifier reports a softmax per square and the board is only as good
# as its weakest one, so that minimum is what the gate looks at.
#
# 0.75 since 2.24.0. Upstream's 0.70 was calibrated against `sharp`
# rasterisation where this port uses Pillow, and it was carried over
# unmeasured. Measured here at last, on 240 renders of the sixteen positions
# in tests/positions.tsv at fifteen scales from 130 to 760 px: at 0.70 the
# gate let through one reading that was wrong, legal, and carried a king a
# side, so nothing downstream said a word about it -- a grid locked one
# square off, scoring 0.73 at its weakest square and 0.93 on average. At 0.75
# that reading is refused and four of 209 correct ones go with it. A refusal
# costs a hand reading; a silent wrong answer costs the verdict, so the trade
# is not symmetric and 2% is cheap.
#
# The gate does not cover this failure mode, it only happens to clip it. A
# grid off by one square classifies every one of its wrong tiles confidently,
# which is why the mean stayed at 0.93. What catches an offset grid is the
# one-king-a-side test and the legality check below, and the compare.py sheet
# after them; this floor is the last of four, not the first.
#
# What the gate is for is worth stating precisely, because the recognizer
# it replaced failed exactly here. That network had no way to say "I do not
# know": on a piece set it was never trained on it returned wrong positions
# at a softmax of 1.000, so no threshold could have caught it. This
# classifier does drop its confidence on an unfamiliar set -- measured 0.46
# on lichess `horsey`, against a floor of 0.7 -- which is what makes a gate
# meaningful at all. It is still a filter on one failure mode and not a
# guarantee: the material count printed by solve.py catches the rest.
UPSTREAM_FLOOR = CONFIDENCE_FLOOR       # 0.70, kept visible so the gap shows
MIN_CONFIDENCE = 0.75

TEXT = {
    "no_board": "No board-like structure found in the image. Crop closer to "
                "the board, or read the diagram by hand -- see "
                "references/reading-diagrams.md",
    "gated_out": "A placement was read but not trusted: the least certain "
                 "square scored {c:.2f}, below {need:.2f}. The usual cause is "
                 "a piece set the classifier does not know; a very small or "
                 "very blurred board does it too. The reading is withheld "
                 "rather than returned, because a wrong piece leaves a "
                 "position that still looks legal and nothing downstream "
                 "would catch it. Read the diagram by hand -- see "
                 "references/reading-diagrams.md -- or lower the bar with "
                 "--confidence if you mean to check the result square by "
                 "square.",
    "implausible": "WARNING: this reading does not have exactly one king a "
                   "side, which usually means the detector locked onto "
                   "something that is not a board. Check it against the "
                   "image before using it.",
    "illegal_read": "The position read here is illegal: {why}. That is a "
                    "statement about the position, not about the reading -- "
                    "composed problems and generated diagrams are illegal all "
                    "the time. Compare the diagram above against the original "
                    "before going further; if they agree, the position is what "
                    "it is.",
    "fatal_read": "The position read here is illegal in a way that leaves the "
                  "engine nothing to do: {why}. No move can be searched from "
                  "it. Re-read the diagram: this is far more often a "
                  "misreading than a real position.",
    "black_view": "Board read from Black's side: the placement is rotated "
                  "180 degrees, {side} to move{auto}",
    "auto": " (from the side the diagram is drawn from)",
    "white": "White", "black": "Black",
    "warn_flip": "WARNING: the pawns run the wrong way -- the diagram looks "
                 "as if it were drawn from {other}'s side. Check the file and "
                 "rank labels and change --view if needed.",
    "read": "Read at {c:.2f} confidence (weakest square; mean {mean:.2f})"
            "{where}",
    "where_snap": ", on the grid-snapped alignment",
    "where_shift": ", on an alignment moved one square: the detected box ran "
                   "past the edge of the image",
    "turn_missing": "Side to move: NOT READ. A diagram in the normal "
                    "orientation does not say whose move it is -- books print "
                    "White at the bottom either way -- so both FENs follow. "
                    "Take the turn from the caption, the question or the user; "
                    "if nothing says and the answer depends on it, ask. Do not "
                    "pass the first line on by default: a tactic solved for "
                    "the wrong side is a confident answer to a different "
                    "question.",
    "fen_if": "FEN if {side} to move: {fen}",
    "turn_forced": "Side to move: {side}. Not a guess: {side}'s king is in "
                   "check, and the side in check is always the side to move.",
    "castling": "Castling rights inferred from the home squares: {rights}. An "
                "image carries no history, so this is a reading too -- a king "
                "that moved and came back would be credited with rights it "
                "does not have.",
    "clock_note": "The halfmove clock is written as 0. That is a claim, not a "
                  "blank: the engine applies the fifty-move rule inside its "
                  "search, and the same endgame can read +2.57 with 0 here "
                  "and 0.00 with 90.",
    "st_import": "importing numpy and onnxruntime",
    "st_model": "loading the model",
    "st_recog": "recognition: {n} pass(es)",
    "st_other": "other",
    "t_header": "\nTime by stage:",
    "t_total": "TOTAL",
    "unit": "s",
}


def t(key, **kw):
    """A template called with nothing to substitute is a bug, not a literal.

    `t("st_recog")` on "recognition: {n} pass(es)" used to return the template
    unchanged, braces and all, and that string went into the timing table and
    into the shared journal. Formatting unconditionally turns it into a
    KeyError at the call site instead.
    """
    return TEXT[key].format(**kw)


_SESSION = None


def session():
    """The model loads once per run."""
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort
        _SESSION = ort.InferenceSession(MODEL_PATH,
                                        providers=["CPUExecutionProvider"])
    return _SESSION


def load_gray(path):
    """Image file -> grayscale (ITU-R 601 luma), downscaled to the cap."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, MAX_DETECT_DIM / max(w, h))
        if scale < 1.0:
            w, h = round(w * scale), round(h * scale)
            im = im.resize((w, h), Image.BILINEAR)
        rgb = np.asarray(im, dtype=np.float32)
    luma = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    return Gray(luma.reshape(-1), w, h)


def classify(img, corners):
    tiles = extract_tiles(img, corners)
    probs = session().run(None, {"tiles": tiles})[0]
    return probs_to_placement(probs)


def is_plausible(placement):
    """Exactly one king a side: the one invariant every real position has.

    Not a legality check and not a substitute for one. A composed study can
    be illegal a dozen ways and still be a real position; what this catches
    is the detector locking onto something that is not a board at all,
    which comes back as a kingless scatter.
    """
    return placement.count("K") == 1 and placement.count("k") == 1


def mask_region(img, box):
    """Flatten a region so its gradients vanish and it cannot be found twice."""
    data = img.data.copy()
    x0 = max(0, int(np.floor(box["x0"])))
    y0 = max(0, int(np.floor(box["y0"])))
    x1 = min(img.width, int(np.ceil(box["x1"])))
    y1 = min(img.height, int(np.ceil(box["y1"])))
    data[y0:y1, x0:x1] = 128
    return Gray(data.reshape(-1), img.width, img.height)


def scan_once(img):
    """Detect, classify, and arbitrate against the grid-snapped candidate.

    The peak search can lock onto an offset grid when the board texture is
    edge-rich -- a hatched book diagram puts more gradient energy inside the
    squares than on the lines. The snapped box is therefore a candidate, not
    a correction: both are classified and the more confident wins.

    Mean confidence decides, not the minimum: one square spoiled by a move
    arrow should not settle which alignment of the board is right.
    """
    corners = find_chessboard_corners(img)
    if not corners:
        return None
    best, best_corners, snapped_won = classify(img, corners), corners, False
    snapped = snap_corners(img, corners)
    if snapped != corners:
        alt = classify(img, snapped)
        if alt["mean_confidence"] > best["mean_confidence"]:
            best, best_corners, snapped_won = alt, snapped, True
    shifted = shift_off_edge(img, best_corners)
    if shifted is not None:
        best, best_corners = classify(img, shifted), shifted
    return {
        **best,
        "corners": best_corners,
        "snapped": snapped_won,
        "shifted": shifted is not None,
        "plausible": is_plausible(best["placement"]),
    }


def off_edge(img, box):
    """Does the box run past the image? A drawn board never does."""
    return (box["x0"] < 0 or box["y0"] < 0
            or box["x1"] > img.width or box["y1"] > img.height)


def shift_off_edge(img, box):
    """A box one square off on BOTH axes, moved back. None when no move is due.

    The detector's parity repair cannot see this case, and the reason is
    arithmetic: its checkerboard score changes sign on a shift of one tile
    along one axis, but a shift along both flips the parity twice and the
    score stays positive. The repair only tries the four one-axis moves in
    any case. What such a box does show is that it hangs off the image --
    measured on a 150 px render, 23..162 on a 150 px canvas -- so that is the
    trigger, and nothing fires on a box that fits.

    The eight neighbours are ranked by checkerboard correlation, NOT by the
    classifier's mean confidence. Tried the other way first: a grid off by a
    square classifies every one of its tiles confidently, and ranking by
    confidence turned 1 silent misread into 2 on the same sweep. Correlation
    looks at the board, not at the pieces, and has no such blind spot.

    Chosen on 255 renders of tests/positions.tsv (219 -> 230 correct, no wrong
    reading of either kind) and then checked on 900 it had never seen -- 30
    random positions, three board themes, ten sizes: 821 -> 846 correct,
    26 -> 0 wrong-but-flagged, 1 -> 0 silent. tests/test_reader.py --sweep
    reruns the second figure.
    """
    if not off_edge(img, box):
        return None
    tile = (box["x1"] - box["x0"]) / 8
    best, best_score = None, checkerboard_score(
        img, box["x0"], box["y0"], box["x1"], box["y1"])
    for sx in (-1, 0, 1):
        for sy in (-1, 0, 1):
            if sx == sy == 0:
                continue
            cand = {"x0": round(box["x0"] + sx * tile),
                    "x1": round(box["x1"] + sx * tile),
                    "y0": round(box["y0"] + sy * tile),
                    "y1": round(box["y1"] + sy * tile)}
            score = checkerboard_score(
                img, cand["x0"], cand["y0"], cand["x1"], cand["y1"])
            if score > best_score:
                best, best_score = cand, score
    return best


def recognize(path, view="white"):
    """Read one image. Returns the reading, or None when no board was found.

    An implausible read is unlikely to be the board that was meant, so the
    region is masked and the scan repeats. The best implausible reading is
    still returned when nothing better turns up -- withholding it would lose
    the case where the position really is unusual -- and the caller decides
    what to do with it through `plausible`.
    """
    img = load_gray(path)
    working = img
    fallback = None
    passes = 0
    for _ in range(MAX_SCAN_PASSES):
        passes += 1
        result = scan_once(working)
        if not result:
            break
        if result["plausible"]:
            result["passes"] = passes
            return _orient(result, view)
        empty_so_far = fallback is None or fallback["placement"] == EMPTY_PLACEMENT
        if empty_so_far and (fallback is None or result["placement"] != EMPTY_PLACEMENT):
            fallback = result
        working = mask_region(working, result["corners"])
    if fallback:
        fallback["passes"] = passes
        return _orient(fallback, view)
    return None


def _orient(result, view):
    """Apply the requested view. The reader always works White-side-up."""
    if view == "black":
        result["placement"] = flip_placement(result["placement"])
    return result


def upside_down(placement):
    """Does the placement look inverted -- judged by pawn direction?

    The only clue available without labels: White's pawns go up and Black's
    go down, so on average White's pawns stand on lower ranks. The test is
    coarse, so it answers only on a clear discrepancy and with enough pawns,
    and returns None when there is nothing to judge by. The legality check
    misses this error entirely, which is why it is worth a warning of its
    own: a board read from the wrong side is legal, plausible, and wrong.
    """
    ranks = placement.split("/")
    if len(ranks) != 8:
        return None
    white, black = [], []
    for row, rank in enumerate(ranks):                  # row 0 is the eighth rank
        for ch in rank:
            if ch == "P":
                white.append(8 - row)
            elif ch == "p":
                black.append(8 - row)
    if len(white) < 3 or len(black) < 3:
        return None
    gap = sum(white) / len(white) - sum(black) / len(black)
    return gap > 0.5 if abs(gap) > 0.5 else None


def journal(rows):
    """Hand the stages to the shared journal (scripts/stage.py --report).

    The journal is created by --start; while it does not exist nothing is
    written.
    """
    path = os.environ.get("CHESS_TIMELINE", "/tmp/chess-verdict-timeline.tsv")
    if not os.path.exists(path):
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            for name, sec, note in rows:
                f.write(f"1\t{name}\t{sec:.3f}\t{' '.join(str(note).split())}\n")
    except OSError:
        pass


def report_stages(stages, started, show):
    """Time by stage. Always journalled, printed on demand."""
    total = time.time() - started
    rows = list(stages)
    rest = total - sum(sec for _, sec, _ in rows)
    if rest > 0.05:
        rows.append((t("st_other"), rest, ""))
    journal(rows)
    if not show:
        return
    texts = [f"{name}, {note}" if note else name for name, _, note in rows]
    width = max(len(x) for x in texts)
    unit = t("unit")
    print(t("t_header"))
    for text, (_, sec, _) in zip(texts, rows):
        share = f"{sec / total * 100:3.0f}%" if total > 0 else "  -"
        print(f"  {text:<{width}}  {sec:6.1f} {unit}  {share}")
    print(f"  {t('t_total'):<{width}}  {total:6.1f} {unit}")


def _status(fen):
    try:
        return chess.Board(fen).status()
    except ValueError:
        return None


def main():
    p = argparse.ArgumentParser(description="Recognize a diagram into a FEN")
    p.add_argument("image")
    p.add_argument("turn", nargs="?", default=None, choices=("w", "b"),
                   help="side to move: w or b. Defaults to b for --view black; "
                        "with the normal view it is not guessed -- both FENs "
                        "are printed unless a check on the board settles it")
    p.add_argument("--view", choices=("white", "black"), default="white",
                   help="which side the board is drawn from: white (labels a, b, "
                        "c, ... along the bottom) or black (h, g, f, ...). With "
                        "black the placement is rotated 180 degrees and the "
                        "default side to move is Black")
    p.add_argument("--engine", choices=ENGINES, default="fenshot",
                   help="which recognizer to use (only one at present)")
    p.add_argument("--confidence", type=float, default=MIN_CONFIDENCE,
                   metavar="P",
                   help=f"reject a reading whose least certain square scores "
                        f"below P (default {MIN_CONFIDENCE}); 0 accepts "
                        f"anything the detector found")
    p.add_argument("--timing", action="store_true",
                   help="print the per-stage breakdown (off by default)")
    args = p.parse_args()
    # `--engine` and `--confidence` are pinned rather than reported only when
    # changed: together they are the reading. A silent wrong answer is this
    # script's one serious failure, the gate is what converts it into a
    # refusal, and a gate whose setting is left to be assumed is half a gate.
    print(banner(p, args, "img2fen", subject=os.path.basename(args.image),
                 pinned=("engine", "confidence"), skip=("image", "turn")))

    # A board turned to Black's side is a strong sign that Black is to move --
    # nobody flips a diagram for the side that is waiting -- so that view still
    # sets the turn, and says so. The normal view carries no such sign: books
    # print White at the bottom whoever is to move. Until 2.25.0 it defaulted to
    # White all the same, with no line saying so, and the FEN it printed passed
    # straight through the side-to-move check solve.py gained in 2.24.0.
    turn = args.turn or ("b" if args.view == "black" else None)
    if args.view == "black":
        print(t("black_view",
                side=t("black") if turn == "b" else t("white"),
                auto="" if args.turn else t("auto")))

    stages = [(t("st_import"), time.time() - _STARTED, "")]

    t0 = time.time()
    session()                                # a separate stage: it happens once
    stages.append((t("st_model"), time.time() - t0, ""))

    t0 = time.time()
    result = recognize(args.image, view=args.view)
    stages.append((t("st_recog", n=result["passes"] if result else 0),
                   time.time() - t0, ""))

    if result is None:
        print(t("no_board"))
        report_stages(stages, _STARTED, args.timing)
        return 1

    placement = result["placement"]
    if result["min_confidence"] < args.confidence:
        print(t("gated_out", c=result["min_confidence"], need=args.confidence))
        report_stages(stages, _STARTED, args.timing)
        return 1

    print(t("read", c=result["min_confidence"], mean=result["mean_confidence"],
            where=(t("where_shift") if result.get("shifted")
                   else t("where_snap") if result["snapped"] else "")))
    rights = infer_castling(placement)
    fens = {s: f"{placement} {s} {rights} - 0 1" for s in "wb"}
    if turn is None:
        # One reading can settle it: the side in check is the side to move.
        possible = [s for s in "wb" if _status(fens[s]) is not None
                    and not _status(fens[s]) & chess.STATUS_OPPOSITE_CHECK]
        if len(possible) == 1:
            turn = possible[0]
            print(t("turn_forced", side=t("white") if turn == "w" else t("black")))
    if turn is None:
        print(t("turn_missing"))
        for s in "wb":
            print(t("fen_if", side=t("white") if s == "w" else t("black"),
                    fen=fens[s]))
    else:
        print(f"FEN: {fens[turn]}")
    print(t("castling", rights=rights))

    if not result["plausible"]:
        print(t("implausible"))

    status = _status(fens[turn or "w"])
    if status is not None and status != chess.STATUS_VALID:
        key = "fatal_read" if status & FATAL_STATUS else "illegal_read"
        print(t(key, why=status_words(status)))

    if upside_down(placement):
        other = t("black") if args.view == "white" else t("white")
        print(t("warn_flip", other=other))

    report_stages(stages, _STARTED, args.timing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
