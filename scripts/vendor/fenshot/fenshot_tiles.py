#!/usr/bin/env python3
"""Tiles and FEN: Python port of fenshot's tiles.ts, fen.ts and compose.ts.

The board is cropped, bilinear-resized to 256x256, normalised to [0,1] and
cut into 64 blocks of 32x32 in the model's own order -- tile k = rank*8 +
file, with a1 at the bottom left. The model then classifies all 64 in one
call.

Edge handling is clamping, not zero padding: a crop that runs a few pixels
outside the image repeats the edge pixel rather than inventing a black
border, because a black border reads as a piece.
"""

from __future__ import annotations

import numpy as np

BOARD_PX = 256
TILE_PX = 32
TILE_INPUT = TILE_PX * TILE_PX

#: Class order of the tile classifier. Index 0 is an empty square.
LABELS = "1KQRBNPkqrbnp"

#: Below this the weakest square is not to be trusted. Upstream's figure.
CONFIDENCE_FLOOR = 0.7


def extract_board_image(img, corners: dict) -> np.ndarray:
    """Bilinear crop-and-resize to 256x256, values in [0, 1]."""
    x0, y0, x1, y1 = corners["x0"], corners["y0"], corners["x1"], corners["y1"]
    cw, ch = x1 - x0, y1 - y0

    t = np.arange(BOARD_PX)
    sy = y0 + (t + 0.5) * ch / BOARD_PX - 0.5
    sx = x0 + (t + 0.5) * cw / BOARD_PX - 0.5
    fy = np.floor(sy).astype(np.int64)
    fx = np.floor(sx).astype(np.int64)
    wy = (sy - fy)[:, None]
    wx = (sx - fx)[None, :]

    def clamp_x(v):
        return np.clip(v, 0, img.width - 1)

    def clamp_y(v):
        return np.clip(v, 0, img.height - 1)

    y_lo, y_hi = clamp_y(fy)[:, None], clamp_y(fy + 1)[:, None]
    x_lo, x_hi = clamp_x(fx)[None, :], clamp_x(fx + 1)[None, :]

    d = img.data
    v = (d[y_lo, x_lo] * (1 - wx) * (1 - wy)
         + d[y_lo, x_hi] * wx * (1 - wy)
         + d[y_hi, x_lo] * (1 - wx) * wy
         + d[y_hi, x_hi] * wx * wy)
    return (v / 255).astype(np.float32)


def board_to_tiles(board: np.ndarray) -> np.ndarray:
    """256x256 board to the [64, 1024] model input."""
    out = np.empty((64, TILE_INPUT), dtype=np.float32)
    for rank in range(8):
        for file in range(8):
            y0 = (7 - rank) * TILE_PX
            x0 = file * TILE_PX
            block = board[y0:y0 + TILE_PX, x0:x0 + TILE_PX]
            out[rank * 8 + file] = block.reshape(-1)
    return out


def extract_tiles(img, corners: dict) -> np.ndarray:
    return board_to_tiles(extract_board_image(img, corners))


def probs_to_placement(probs: np.ndarray) -> dict:
    """Model output to a FEN placement field, plus the confidences.

    The board is only as good as its weakest square, so the minimum is
    what the caller gates on; the mean is what arbitrates between two
    candidate alignments of the same board.
    """
    probs = probs.reshape(64, 13)
    idx = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    names = [LABELS[i] for i in idx]
    ranks = ["".join(names[r * 8:r * 8 + 8]) for r in range(7, -1, -1)]
    placement = "/".join(_compress(rank) for rank in ranks)
    return {
        "placement": placement,
        "confidences": [float(c) for c in conf],
        "min_confidence": float(conf.min()),
        "mean_confidence": float(conf.mean()),
    }


def _compress(rank: str) -> str:
    """Run-length compression of empty squares, as FEN wants it."""
    out, empty = "", 0
    for ch in rank:
        if ch == "1":
            empty += 1
        else:
            if empty:
                out += str(empty)
                empty = 0
            out += ch
    return out + (str(empty) if empty else "")


def flip_placement(placement: str) -> str:
    """Rotate 180 degrees: for a board drawn from Black's side."""
    return "/".join(rank[::-1] for rank in placement.split("/")[::-1])


def _mean_pawn_ranks(placement: str):
    white, black = [], []
    for i, row in enumerate(placement.split("/")):
        rank = 8 - i
        for ch in row:
            if ch == "P":
                white.append(rank)
            elif ch == "p":
                black.append(rank)
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return mean(white), mean(black)


def resolve_orientation(placement: str) -> tuple[str, str]:
    """Decide which side the board is drawn from, by pawn direction.

    The one orientation-fixed fact in chess: White's pawns march up the
    ranks and Black's march down, so in any natural position White's pawns
    sit on average lower. The reader always works as if White were at the
    bottom, so a diagram drawn from Black's side comes back with that
    relationship inverted.

    When either side has no pawns the test says nothing, and this returns
    the reading unchanged rather than guessing -- an orientation guessed
    from a pawnless position is a rotated board with no symptom.
    """
    def naturalness(p):
        white, black = _mean_pawn_ranks(p)
        return None if white is None or black is None else black - white

    as_read = naturalness(placement)
    rotated = flip_placement(placement)
    as_rotated = naturalness(rotated)
    if as_read is not None and as_rotated is not None and as_rotated > as_read:
        return rotated, "black"
    return placement, "white"


def _expand(rank: str) -> str:
    out = ""
    for ch in rank:
        out += "." * int(ch) if ch.isdigit() else ch
    return out


def infer_castling(placement: str) -> str:
    """Castling rights from the home squares, since an image carries no history.

    This is a reading, unlike the unconditional '-' the older recognizer
    wrote. King and rook still at home keep the right; anything else drops
    it. It is a guess in one direction only -- a king that has moved and
    returned would be credited with rights it does not have -- but it is
    right far more often than a blanket '-', which costs 0.1 to 0.3 pawns
    in an opening position and the whole answer where castling is the
    solution.
    """
    rows = placement.split("/")
    if len(rows) != 8:
        return "-"
    white, black = _expand(rows[7]), _expand(rows[0])
    rights = ""
    if white[4] == "K":
        if white[7] == "R":
            rights += "K"
        if white[0] == "R":
            rights += "Q"
    if black[4] == "k":
        if black[7] == "r":
            rights += "k"
        if black[0] == "r":
            rights += "q"
    return rights or "-"


def placement_to_fen(placement: str, turn: str) -> str:
    """A full FEN. En passant and both clocks are unknowable from an image.

    The halfmove clock is written as 0, and that zero is a claim, not a
    blank: the engine applies the fifty-move rule inside its search, so the
    same endgame reads +2.57 with 0 here and 0.00 with 90. Where the
    verdict is a long win, say the reading assumes a freshly reset counter.
    """
    return f"{placement} {turn} {infer_castling(placement)} - 0 1"
