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
"""Tests for compare.py -- the board detector and the comparison sheet.

    python3 tests/test_compare.py

The detector is the part worth testing. It has no engine and no ground truth of
its own: it looks at pixels and decides where the board is, and when it is wrong
the whole comparison silently misaligns by half a square, which is exactly the
kind of error the comparison exists to catch. So the fixtures here are diagrams
built to known coordinates -- the answer is known to the pixel, and the test
asserts the box lands within a few pixels of it.

The grey-label fixture is the regression: the first version of the detector
matched anti-aliased grey text around (200,200,200) as though it were a light
square, and grew the box to swallow the coordinate margin.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "scripts"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import compare  # noqa: E402

FEN = "7K/4P1p1/6Pk/3p2pP/1p4P1/1P1p4/3P4/8 w - - 0 1"
LIGHT, DARK = (240, 217, 181), (181, 136, 99)

failures = []


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


def diagram(board_px=640, margin_left=60, margin_top=20, margin_right=20,
            margin_bottom=60, labels=True, background=(245, 244, 241)):
    """A synthetic diagram with the board at a known offset."""
    w = margin_left + board_px + margin_right
    h = margin_top + board_px + margin_bottom
    im = Image.new("RGB", (w, h), background)
    d = ImageDraw.Draw(im)
    step = board_px / 8
    for r in range(8):
        for f in range(8):
            colour = LIGHT if (r + f) % 2 == 0 else DARK
            x0 = margin_left + f * step
            y0 = margin_top + r * step
            d.rectangle([x0, y0, x0 + step, y0 + step], fill=colour)
    if labels:
        try:
            font = ImageFont.truetype(compare.FONT, 26)
        except OSError:
            font = ImageFont.load_default()
        for i, ch in enumerate("87654321"):
            d.text((margin_left - 30, margin_top + i * step + step / 2), ch,
                   fill=(150, 150, 150), font=font, anchor="mm")
        for i, ch in enumerate("abcdefgh"):
            d.text((margin_left + i * step + step / 2,
                    margin_top + board_px + 28), ch,
                   fill=(150, 150, 150), font=font, anchor="mm")
    return im, (margin_left, margin_top, margin_left + board_px,
                margin_top + board_px)


def close(box, want, slack=4):
    return box is not None and all(abs(a - b) <= slack for a, b in zip(box, want))


def test_finds_the_board():
    im, want = diagram()
    got = compare.board_box(im)
    check("the board is located to within a few pixels", close(got, want),
          f"{got} wanted {want}")


def test_grey_labels_are_not_board():
    """The regression: grey text used to be read as light squares."""
    im, want = diagram(margin_left=90, margin_bottom=90)
    got = compare.board_box(im)
    check("coordinate labels stay outside the box", close(got, want),
          f"{got} wanted {want}")


def test_monochrome_board_is_found():
    """A book diagram is grey, and grey used to make the board disappear.

    The saturation filter that keeps coordinate labels out also removed every
    unsaturated board, and on such a diagram the light squares merge with the
    paper into a single colour bin, so the two dominant colours are paper and
    dark squares rather than the two square colours. The fallback keeps the
    darker one alone: a1 and h8 are dark on every board drawn from either
    side, so the dark squares' bounding box is the board's.
    """
    global LIGHT, DARK
    keep, (LIGHT, DARK) = (LIGHT, DARK), ((235, 235, 235), (150, 150, 150))
    try:
        im, want = diagram()
        got = compare.board_box(im)
    finally:
        LIGHT, DARK = keep
    check("a grey board is found, labels and all", got is not None and close(got, want),
          f"{got} wanted {want}")


def test_tight_crop():
    im, want = diagram(margin_left=0, margin_top=0, margin_right=0,
                       margin_bottom=0, labels=False)
    got = compare.board_box(im)
    check("an already-cropped board is left alone", close(got, want),
          f"{got} wanted {want}")


def test_refuses_when_not_square():
    """A wide crop is not a board; the caller must fall back, not guess."""
    im, _ = diagram(labels=False)
    wide = Image.new("RGB", (im.width + 700, im.height), (245, 244, 241))
    wide.paste(im, (0, 0))
    strip = Image.new("RGB", (600, 120), LIGHT)
    wide.paste(strip, (im.width + 60, 40))
    got = compare.board_box(wide)
    check("a non-square candidate is refused", got is None, str(got))


def test_sheet_is_written():
    im, _ = diagram()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src.png")
        out = os.path.join(tmp, "out.png")
        im.save(src)
        r = subprocess.run([sys.executable, compare.__file__, src, FEN,
                            "-o", out], capture_output=True, text=True)
        ok = r.returncode == 0 and os.path.exists(out)
        check("the comparison sheet is written", ok,
              (r.stderr.strip() or "")[:80])
        if ok:
            sheet = Image.open(out)
            check("both boards are on it at full size",
                  sheet.width > 2 * compare.SIZE, f"{sheet.width}px wide")


def test_mono_leaves_the_source_alone():
    """Grey is the default rendering now; the asymmetry is still the point.

    Desaturating the source too was the first version and it destroyed a green
    last-move highlight without leaving a trace on the sheet. A test that only
    checked "the sheet came out grey" would have passed on that version.
    """
    im, _ = diagram()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src.png")
        im.save(src)
        sheets = {}
        for name, extra in (("plain", []), ("color", ["--no-mono"])):
            out = os.path.join(tmp, name + ".png")
            r = subprocess.run([sys.executable, compare.__file__, src, FEN,
                                "-o", out] + extra,
                               capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(out):
                check(f"{name or 'plain'} run", False,
                      (r.stderr.strip() or "")[:80])
                return
            sheets[name] = Image.open(out).convert("RGB")

        left = sheets["plain"].crop((0, 0, compare.SIZE, sheets["plain"].height))
        left_color = sheets["color"].crop((0, 0, compare.SIZE,
                                           sheets["color"].height))
        check("--no-mono leaves the source half untouched",
              left.tobytes() == left_color.tobytes())

        right = sheets["plain"].crop((sheets["plain"].width - compare.SIZE, 0,
                                      sheets["plain"].width,
                                      sheets["plain"].height))
        right_color = sheets["color"].crop((sheets["color"].width - compare.SIZE, 0,
                                            sheets["color"].width,
                                            sheets["color"].height))
        check("--no-mono redraws the rendered half",
              right.tobytes() != right_color.tobytes())

        px = np.asarray(right, dtype=int)
        neutral = (np.abs(px[..., 0] - px[..., 1]) < 6) & (
            np.abs(px[..., 1] - px[..., 2]) < 6)
        share = neutral.mean()
        check("the rendered half comes out grey by default", share > 0.9,
              f"{share:.3f} neutral")


def test_bad_fen_is_rejected():
    im, _ = diagram()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src.png")
        im.save(src)
        r = subprocess.run([sys.executable, compare.__file__, src,
                            "not-a-fen", "-o", os.path.join(tmp, "o.png")],
                           capture_output=True, text=True)
        check("an unparseable FEN is refused, not drawn",
              r.returncode == 2, f"exit {r.returncode}")


if __name__ == "__main__":
    for fn in (test_finds_the_board, test_grey_labels_are_not_board,
               test_monochrome_board_is_found,
               test_tight_crop, test_refuses_when_not_square,
               test_sheet_is_written, test_mono_leaves_the_source_alone,
               test_bad_fen_is_rejected):
        fn()
    print()
    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")
