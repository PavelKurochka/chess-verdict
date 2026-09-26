#!/usr/bin/env python3
"""Chessboard detection in a screenshot: Python port of fenshot's detect.ts.

Upstream is `scoriiu/fenshot` (MIT), itself a TypeScript port of
`chessboard_finder.py` from Elucidation/tensorflow_chessbot (MIT). So this
file closes a loop: Python -> TypeScript -> Python. The middle hop is not
wasted, because the TS version carries fixes the original does not (the
noise pre-gate removal, the signed checkerboard score, the parity repair,
the one-axis reconstruction), and those are what this port follows.

Faithfulness is the whole point, so the quirks are ported rather than
tidied: the strict `<` against the left window and `<=` against the right
one in the non-maximum suppression, the right window that stops one short
of the end, the duplicate check inside the sequence search. Every one of
them changes which peaks survive, and the goldens in the upstream repo
pin the result to two pixels.

Algorithm: image gradients split into positive and negative parts, summed
into a 1D response per row and per column. Board edges make strong evenly
spaced peaks; arithmetic sequences of at least seven of them are the seven
inner lines of an 8x8 board. Among the candidate sub-grids, the one whose
crop correlates best with an ideal checkerboard wins.
"""

from __future__ import annotations

import numpy as np

PEAK_KEEP_RATIO = 0.2
MIN_SEQ_LEN = 7
ERR_PX = 5
MAX_CANDIDATE_SEQS = 5

NEG_INF = float("-inf")


class Gray:
    """A grayscale image: float32 values 0-255, row-major."""

    __slots__ = ("data", "width", "height")

    def __init__(self, data: np.ndarray, width: int, height: int):
        self.data = np.asarray(data, dtype=np.float32).reshape(height, width)
        self.width = width
        self.height = height

    def at(self, x: int, y: int) -> float:
        """Zero outside the image -- the checkerboard score pads with zeros."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return float(self.data[y, x])
        return 0.0


def _window_max(arr: np.ndarray, start: int, stop: int) -> float:
    """max over [start, stop); -inf on an empty window, as JS Math.max does."""
    if stop <= start:
        return NEG_INF
    return float(arr[start:stop].max())


def hough_response(grad: np.ndarray, axis: str) -> np.ndarray:
    """response[i] = sum(positive part) * sum(negative part) along the axis.

    A grid line shows up as a rise followed by a fall, so the product is
    large only where both are; a one-sided edge (a window border, a page
    margin) scores near zero.
    """
    pos = np.clip(grad, 0, None)
    neg = np.clip(-grad, 0, None)
    along = 1 if axis == "rows" else 0
    return pos.sum(axis=along).astype(np.float64) * neg.sum(axis=along).astype(np.float64)


def nonmax_suppress(arr: np.ndarray, winsize: int = 5) -> np.ndarray:
    """Faithful port of nonmax_suppress_1d, edge quirks included.

    The asymmetry is not a typo upstream: a peak is kept when it strictly
    beats its left window and strictly-or-equally beats its right one, and
    the right window stops one element short of the end. Ties therefore
    resolve leftwards. Changing this moves peaks by a pixel and the golden
    corners stop matching.
    """
    out = arr.astype(np.float64).copy()
    n = len(arr)
    for i in range(n):
        left = 0.0 if i == 0 else _window_max(arr, max(0, i - winsize), i)
        right = 0.0 if i >= n - 2 else _window_max(arr, i + 1, min(n - 1, i + winsize))
        if arr[i] < left or arr[i] <= right:
            out[i] = 0.0
    return out


def all_sequences(seq: list[int]) -> list[list[int]]:
    """Every arithmetic sequence (within ERR_PX) of length >= MIN_SEQ_LEN."""
    if len(seq) < MIN_SEQ_LEN:
        return []
    arr = np.asarray(seq, dtype=np.float64)
    seqs: list[list[int]] = []
    for i in range(len(seq) - 1):
        for j in range(i + 1, len(seq)):
            duplicate = False
            for prev in seqs:
                for k in range(len(prev) - 1):
                    if seq[i] == prev[k] and seq[j] == prev[k + 1]:
                        duplicate = True
            if duplicate:
                continue
            d = seq[j] - seq[i]
            if d < ERR_PX:
                continue
            s = [seq[i], seq[j]]
            n = s[-1] + d
            while True:
                dist = np.abs(arr - n)
                best_idx = int(dist.argmin())
                if dist[best_idx] >= ERR_PX:
                    break
                s.append(seq[best_idx])
                n = s[-1] + d
            if len(s) >= MIN_SEQ_LEN:
                seqs.append(s)
    return seqs


def trim_sequence(seq: list[int], vals: list[float]) -> tuple[list[int], list[float]]:
    """Strip the weakest end until at most nine lines remain."""
    s, v = list(seq), list(vals)
    if len(s) > 9:
        while len(s) > 7:
            if v[0] > v[-1]:
                s, v = s[:-1], v[:-1]
            else:
                s, v = s[1:], v[1:]
    return s, v


def median(values) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else float((s[mid - 1] + s[mid]) / 2)


def checkerboard_score(img: Gray, x0: int, y0: int, x1: int, y1: int) -> float:
    """Nearest-neighbour crop to 64x64, correlated against an ideal board.

    Signed on purpose. The kernel's +1 cells sit on the crop's corner
    parity, and a chessboard's corner squares are the light ones in either
    orientation, so a correctly aligned crop correlates positive. A crop
    shifted by an odd number of tiles inverts the parity and goes negative
    -- which is exactly what lets `repair_parity` below notice that the
    grid was found but placed one tile off. An absolute value here scores
    the wrong box as high as the right one.
    """
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return 0.0
    ty = np.arange(64)
    sy = y0 + (ty * h) // 64
    sx = x0 + (ty * w) // 64          # same arithmetic on both axes
    ys, xs = np.meshgrid(sy, sx, indexing="ij")
    inside = (xs >= 0) & (xs < img.width) & (ys >= 0) & (ys < img.height)
    px = np.zeros((64, 64), dtype=np.float64)
    px[inside] = img.data[ys[inside], xs[inside]]
    parity = np.where(((ty[:, None] // 8) + (ty[None, :] // 8)) % 2 == 0, 1.0, -1.0)
    # parity is [ty, tx]; the kernel is symmetric in the two indices so the
    # orientation of the meshgrid does not matter here.
    return float((parity * px).sum() / 64)


def ranked_peak_sequences(hough: np.ndarray) -> list[dict]:
    """Candidate line sequences, best average peak value first.

    Several are kept rather than only the best: piece edges and adjacent
    interface lines can form a shifted arithmetic sequence whose peaks
    narrowly beat the true grid's. Peak strength cannot separate those;
    checkerboard correlation can, and it runs later.
    """
    suppressed = nonmax_suppress(hough)
    peak = suppressed.max() if len(suppressed) else 0.0
    if peak <= 0:
        return []
    norm = suppressed / peak
    keep = np.nonzero(norm >= PEAK_KEEP_RATIO)[0]
    positions = [int(p) for p in keep]
    value_at = {int(p): float(norm[p]) for p in keep}
    seqs = all_sequences(positions)
    if not seqs:
        return []
    scored = []
    for s in seqs:
        vals = [value_at.get(p, 0.0) for p in s]
        t_seq, t_vals = trim_sequence(s, vals)
        scored.append((sum(t_vals) / len(t_vals), {"trimmed": t_seq, "full": s}))
    scored.sort(key=lambda item: item[0], reverse=True)
    unique: list[dict] = []
    for _score, cand in scored:
        if not any(u["full"] == cand["full"] for u in unique):
            unique.append(cand)
        if len(unique) >= MAX_CANDIDATE_SEQS:
            break
    return unique


def snap_corners(img: Gray, box: dict) -> dict:
    """Refine the box a few pixels either way by checkerboard correlation.

    The peak search can lock onto an offset grid when the board texture is
    edge-rich -- a hatched book diagram puts more gradient energy inside
    the squares than on the lines. This is a candidate, not a correction:
    the caller classifies both boxes and keeps whichever the tile model is
    more confident about.
    """
    tile = (box["x1"] - box["x0"]) / 8
    radius = max(2, round(tile / 3))
    best = {"dx": 0, "dy": 0, "score": NEG_INF}

    def evaluate(dx: int, dy: int) -> None:
        score = checkerboard_score(
            img, box["x0"] + dx, box["y0"] + dy, box["x1"] + dx, box["y1"] + dy)
        if score > best["score"]:
            best.update(dx=dx, dy=dy, score=score)

    for dy in range(-radius, radius + 1, 2):
        for dx in range(-radius, radius + 1, 2):
            evaluate(dx, dy)
    cx, cy = best["dx"], best["dy"]
    for dy in range(cy - 2, cy + 3):
        for dx in range(cx - 2, cx + 3):
            evaluate(dx, dy)
    return {"x0": box["x0"] + best["dx"], "y0": box["y0"] + best["dy"],
            "x1": box["x1"] + best["dx"], "y1": box["y1"] + best["dy"]}


def reconstruct_square_board(img: Gray, good: list[int], axis: str):
    """Rebuild the weak axis from the good one, because a board is square.

    Fires when the grid lines are clean on one axis and drowned on the
    other -- pale themes where the black pieces dump more gradient energy
    than the faint grid. The extent on the weak axis equals eight tiles of
    the good axis's spacing; slide that square window and keep the best
    correlation. It cannot manufacture a board out of noise: the score
    arbitrates, and a flat region scores near zero.
    """
    if len(good) < 2:
        return None
    tile = median([good[i + 1] - good[i] for i in range(len(good) - 1)])
    if not tile > 0:
        return None
    g_a, g_b = round(good[0]), round(good[-1])
    if g_b - g_a <= 0:
        return None
    pad = round(tile)
    extents = [(g_a, g_b)]
    for k in range(0, len(good) - 6):
        e = (round(good[k]) - pad, round(good[k + 6]) + pad)
        if not any(abs(a - e[0]) <= 2 and abs(b - e[1]) <= 2 for a, b in extents):
            extents.append(e)
    limit = img.height if axis == "x" else img.width

    best_box, best_score = None, NEG_INF
    for e_a, e_b in extents:
        span = e_b - e_a
        step = max(2, round(tile / 8))
        for start in range(-span, limit + 1, step):
            w_a, w_b = start, start + span
            box = ({"x0": e_a, "y0": w_a, "x1": e_b, "y1": w_b} if axis == "x"
                   else {"x0": w_a, "y0": e_a, "x1": w_b, "y1": e_b})
            score = checkerboard_score(img, box["x0"], box["y0"], box["x1"], box["y1"])
            if score > best_score:
                best_score, best_box = score, box
    return (best_box, best_score) if best_box else None


def reconstruct_from_candidates(img: Gray, candidates: list[dict], axis: str):
    """The same reconstruction across every candidate sequence.

    The full, untrimmed line list is used: the trim ranks by peak value,
    and a phantom line -- the board's outer edge, a neighbouring interface
    rule -- often carries a stronger peak than a true grid line.
    """
    best, best_score = None, NEG_INF
    for cand in candidates:
        r = reconstruct_square_board(img, cand["full"], axis)
        if r and r[1] > best_score:
            best, best_score = r[0], r[1]
    return best


def repair_parity(img: Gray, box: dict) -> dict:
    """A negative correlation means the box is a whole tile off; fix it.

    The grid was found, but an outer edge displaced an inner line in the
    peak sequence and shifted everything by one square. The symptom is
    nasty precisely because nothing downstream notices: the position reads
    cleanly, at high confidence, with every piece one file across.
    """
    score = checkerboard_score(img, box["x0"], box["y0"], box["x1"], box["y1"])
    if score >= 0:
        return box
    tile = round((box["x1"] - box["x0"]) / 8)
    best, best_score = box, score
    for sx, sy in ((tile, 0), (-tile, 0), (0, tile), (0, -tile)):
        c = {"x0": box["x0"] + sx, "y0": box["y0"] + sy,
             "x1": box["x1"] + sx, "y1": box["y1"] + sy}
        s = checkerboard_score(img, c["x0"], c["y0"], c["x1"], c["y1"])
        if s > best_score:
            best, best_score = c, s
    return best


def find_chessboard_corners(img: Gray):
    """The board's bounding box, or None when no board-like structure is found."""
    grad_y = np.gradient(img.data.astype(np.float64), axis=0)
    grad_x = np.gradient(img.data.astype(np.float64), axis=1)
    hough_rows = hough_response(grad_y, "rows")
    hough_cols = hough_response(grad_x, "cols")

    candidates_y = ranked_peak_sequences(hough_rows)
    candidates_x = ranked_peak_sequences(hough_cols)
    lines_y = candidates_y[0]["trimmed"] if candidates_y else None
    lines_x = candidates_x[0]["trimmed"] if candidates_x else None

    if lines_x and not lines_y:
        r = reconstruct_from_candidates(img, candidates_x, "x")
        return repair_parity(img, r) if r else None
    if lines_y and not lines_x:
        r = reconstruct_from_candidates(img, candidates_y, "y")
        return repair_parity(img, r) if r else None
    if not lines_x or not lines_y:
        return None

    dx = median([lines_x[i + 1] - lines_x[i] for i in range(len(lines_x) - 1)])
    dy = median([lines_y[i + 1] - lines_y[i] for i in range(len(lines_y) - 1)])

    sub_x = [lines_x[k:k + 7] for k in range(0, len(lines_x) - 6)]
    sub_y = [lines_y[k:k + 7] for k in range(0, len(lines_y) - 6)]

    best, best_score = None, NEG_INF
    for sx in sub_x:
        for sy in sub_y:
            box = {"x0": round(sx[0] - dx), "x1": round(sx[6] + dx),
                   "y0": round(sy[0] - dy), "y1": round(sy[6] + dy)}
            score = checkerboard_score(img, box["x0"], box["y0"], box["x1"], box["y1"])
            if score > best_score:
                best_score, best = score, box
    return repair_parity(img, best) if best else None
