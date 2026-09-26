# Vendored: fenshot

The tile classifier `chess-tiles-v2.onnx` (1.29 MB) is taken verbatim from
`scoriiu/fenshot` (MIT, see LICENSE). `fenshot_detect.py` and
`fenshot_tiles.py` are a Python port of that project's `detect.ts`,
`tiles.ts`, `fen.ts` and `compose.ts`.

The chain is a loop: the original `chessboard_finder.py` in
Elucidation/tensorflow_chessbot (MIT, © 2016 Sameer Ansari — notice retained
in LICENSE below fenshot's) was Python, fenshot ported it to
TypeScript, and this brings it back. The middle hop is not wasted --
fenshot carries fixes the original lacks: the scale-dependent noise
pre-gate removed, a signed checkerboard correlation instead of an
absolute one, the parity repair, and the one-axis reconstruction.

Faithfulness matters more than tidiness here, so the quirks are ported
rather than cleaned up: the asymmetric comparisons in the non-maximum
suppression, the right window that stops one element short, the duplicate
check inside the sequence search. Each changes which peaks survive.

## How the port was verified

Against the upstream goldens, all three levels:

| check | tolerance | result |
|---|---|---|
| detector corners on the reference image | +/- 2 px | exact: 30, 14, 542, 526 |
| tile tensor against the PIL goldens | mean < 0.01, max < 0.25 | 0.0079, 0.229 |
| eight real screenshots vs `testset-manifest.json` | -- | 8 of 8 |

A ninth fixture, a page with no board on it, is refused as it should be.

## Where this differs from upstream

Upstream rasterises with `sharp` (libvips); this uses Pillow. The readings
agree on every fixture, the confidences do not: `chesscom-italian-white`
scores 0.893 under sharp and 0.764 under Pillow. CONFIDENCE_FLOOR is
upstream's 0.7, so that margin is thinner here than the authors measured.
It has never fired on the piece-set stand -- all 200 readings cleared it --
so there is no local calibration for it yet. Treat 0.7 as inherited, not
as measured on this pipeline.

The npm package at 0.1.4 also lags the repository: it has no `plausible`
check (`grep -c plausible` gives 9 in the sources and 0 in `dist`). The
port follows the repository, so the check is present here.
