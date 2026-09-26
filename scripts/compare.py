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
"""Put the source diagram and the position as read side by side, grids aligned.

The reading check in step 4 asks for the rendered board to be compared against
the original, and until now that comparison was made across two separate images
of different sizes, in different piece styles, one of them carrying its own
coordinate labels. Aligning them is the whole difficulty: once both boards are
cropped to their outer edge and scaled to the same pixel size, square e4 is at
the same place in both, and a misread piece is visible without counting files.

    python3 compare.py board.jpg "<FEN>" -o compare.png

The source board is located by colour: on a 2D diagram the two square colours
are by far the most common pixels, so the bounding box of everything matching
them is the board. That fails on a photograph of a physical board and on a
diagram whose margin is the same colour as its light squares, so the result is
checked for being roughly square and large enough, and the script falls back to
the uncropped image with a warning rather than cropping to nonsense.

The rendered half is grey by default, not python-chess's brown. The two halves
are almost never in the same palette to begin with, and that difference in hue
is the first thing the eye reads on a sheet where the only question is whether
a piece stands on the same square in both. Neutral grey on the rendered side
removes the comparison the sheet was never asking for. `--no-mono` goes back to
the brown rendering, for the case where matching the source's own palette is
what is wanted.

Only the rendered half is ever touched by this. Desaturating the source as well
was tried and reverted: the source is the evidence, and any processing of it
can hide something. It did — a diagram with its last move highlighted in green
lost the highlight to grey, and the sheet gave no sign that anything had been
dropped.
"""

import argparse
import os
import subprocess
import sys
import tempfile

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - environment, not logic
    sys.exit("compare.py needs Pillow and NumPy (%s). Install them with:\n"
             "  pip install pillow numpy --break-system-packages -q" % exc)

try:
    import chess
    import chess.svg
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

SIZE = 768           # both boards are rendered at this pixel size
GAP = 28
MARGIN = 20
LABEL_H = 34
MONO_COLOURS = {"square light": "#f0f0f0", "square dark": "#b8b8b8"}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size, bold=False):
    path = FONT_BOLD if bold else FONT
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def board_box(img, tolerance=40):
    """Bounding box of the board inside a 2D diagram, or None if unsure.

    The two square colours dominate the pixel histogram of any diagram that is
    mostly board. Quantising to 32 levels a channel groups the anti-aliased
    edges with their own square, so the two top bins are the two colours even
    on a JPEG.
    """
    a = np.asarray(img.convert("RGB")).astype(int)
    q = a // 32
    flat = q.reshape(-1, 3)
    keys, counts = np.unique(flat, axis=0, return_counts=True)
    parts = []
    for key in keys[np.argsort(-counts)[:2]]:
        # The centroid of the bin, not its corner: a bin corner can sit 30-odd
        # levels away from every pixel actually in it, which is most of the
        # tolerance budget spent before any real variation is allowed for.
        member = (q == key).all(axis=2)
        centroid = a[member].mean(axis=0)
        parts.append((centroid.mean(), np.abs(a - centroid).max(axis=2) <= tolerance))
    mask = parts[0][1] | parts[1][1] if len(parts) == 2 else parts[0][1]
    # Board squares are coloured; the grey of coordinate labels is not. Without
    # this, anti-aliased grey text around (200,200,200) lands within tolerance of
    # a light tan and the box grows to include the whole label margin.
    saturated = a.max(axis=2) - a.min(axis=2) >= 25
    if (mask & saturated).sum() >= 0.5 * mask.sum():
        mask &= saturated
    elif len(parts) == 2:
        # A monochrome diagram -- a scanned book page, a grey theme -- has no
        # saturation to filter on, and its light squares are within tolerance of
        # the paper itself, so the two merge into one bin. The dark squares are
        # the one part of such a diagram that cannot be confused with paper, and
        # their bounding box IS the board's: a1 and h8 are dark on every board,
        # drawn from either side. So fall back to the darker of the two.
        mask = min(parts)[1]
    # Rows and columns, not stray pixels: a real board row is board across most
    # of its width, so requiring that ignores anything scattered outside it.
    row_frac, col_frac = mask.mean(axis=1), mask.mean(axis=0)
    rows = np.where(row_frac > 0.5 * row_frac.max())[0]
    cols = np.where(col_frac > 0.5 * col_frac.max())[0]
    if len(rows) < 8 or len(cols) < 8:
        return None
    box = (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)
    w, h = box[2] - box[0], box[3] - box[1]
    # A board is square and takes up most of a diagram. Either failing means the
    # detection has locked onto something else -- better to show the whole image.
    if min(w, h) / max(w, h) < 0.9:
        return None
    if w * h < 0.25 * img.width * img.height:
        return None
    return box


def render_fen(fen, path, flipped=False, mono=True):
    """The position as read, with no coordinates, so the 8x8 grids line up."""
    board = chess.Board(fen)
    svg = chess.svg.board(board, size=SIZE, coordinates=False, orientation=(
        chess.BLACK if flipped else chess.WHITE),
        colors=dict(MONO_COLOURS) if mono else {})
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg)
        tmp = f.name
    try:
        for tool in (["rsvg-convert", "-o", path, tmp],
                     ["cairosvg", tmp, "-o", path]):
            try:
                if subprocess.run(tool, capture_output=True).returncode == 0:
                    return True
            except FileNotFoundError:
                continue
        return False
    finally:
        # In a finally: the old code removed the file on both returns but not
        # when subprocess raised anything other than FileNotFoundError.
        os.remove(tmp)


def grid(draw, x0, y0, colour=(0, 0, 0), width=1):
    """Eight-by-eight rule over both boards: it is what makes them comparable."""
    step = SIZE / 8
    for i in range(1, 8):
        draw.line([(x0 + i * step, y0), (x0 + i * step, y0 + SIZE)],
                  fill=colour, width=width)
        draw.line([(x0, y0 + i * step), (x0 + SIZE, y0 + i * step)],
                  fill=colour, width=width)
    draw.rectangle([x0, y0, x0 + SIZE, y0 + SIZE], outline=colour, width=width)


def coordinates(draw, x0, y0, flipped=False):
    step = SIZE / 8
    f = font(19)
    files = "abcdefgh" if not flipped else "hgfedcba"
    ranks = "87654321" if not flipped else "12345678"
    for i in range(8):
        draw.text((x0 + i * step + step / 2, y0 + SIZE + 6), files[i],
                  fill=(90, 90, 90), font=f, anchor="ma")
        draw.text((x0 - 8, y0 + i * step + step / 2), ranks[i],
                  fill=(90, 90, 90), font=f, anchor="rm")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("image", help="the source diagram")
    p.add_argument("fen", help="the position as read")
    p.add_argument("-o", "--out", default="compare.png")
    p.add_argument("--no-crop", action="store_true",
                   help="use the source image whole, without locating the board")
    p.add_argument("--no-grid", action="store_true")
    p.add_argument("--flipped", action="store_true",
                   help="the diagram is drawn from Black's side")
    p.add_argument("--view", choices=("white", "black"), default=None,
                   help="the same as --flipped when black; the spelling "
                        "img2fen.py and solve.py use")
    p.add_argument("--no-mono", dest="mono", action="store_false",
                   default=True,
                   help="draw the rendered board in python-chess's brown "
                        "instead of grey; the source is left untouched "
                        "either way")
    p.add_argument("--left-label", default="source diagram")
    p.add_argument("--right-label", default="position as read")
    args = p.parse_args()
    if args.view:
        args.flipped = args.view == "black"

    try:
        chess.Board(args.fen)
    except ValueError as exc:
        print(f"not a legal FEN: {exc}", file=sys.stderr)
        return 2

    src = Image.open(args.image).convert("RGB")
    note = ""
    if not args.no_crop:
        box = board_box(src)
        if box is None:
            note = ("the board could not be located in the source; "
                    "the whole image is shown and the grids may not align")
            print(f"warning: {note}", file=sys.stderr)
        else:
            src = src.crop(box)
    src = src.resize((SIZE, SIZE), Image.LANCZOS)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        rendered_path = f.name
    if not render_fen(args.fen, rendered_path, args.flipped, args.mono):
        os.remove(rendered_path)
        print("no rasteriser: install librsvg2-bin or cairosvg", file=sys.stderr)
        return 3
    rendered = Image.open(rendered_path).convert("RGB").resize(
        (SIZE, SIZE), Image.LANCZOS)

    left = MARGIN + 26
    top = MARGIN + LABEL_H
    width = left + SIZE + GAP + SIZE + MARGIN
    height = top + SIZE + 30 + MARGIN + (24 if note else 0)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    sheet.paste(src, (left, top))
    sheet.paste(rendered, (left + SIZE + GAP, top))

    draw = ImageDraw.Draw(sheet)
    for x0, label in ((left, args.left_label),
                      (left + SIZE + GAP, args.right_label)):
        draw.text((x0 + SIZE / 2, top - 10), label, fill=(20, 20, 20),
                  font=font(23, bold=True), anchor="ms")
        if not args.no_grid:
            grid(draw, x0, top, colour=(0, 0, 0, 255))
        coordinates(draw, x0, top, args.flipped)
    if note:
        draw.text((left, height - MARGIN - 8), "note: " + note,
                  fill=(150, 60, 40), font=font(17), anchor="ls")

    sheet.save(args.out)
    os.remove(rendered_path)
    print(f"wrote {args.out}  ({sheet.width}x{sheet.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
