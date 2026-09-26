# chess-verdict

*A position in, a verdict out: the move, the line behind it, and how far it was actually proved.*

An [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
that analyses a chess position with Stockfish. A diagram image or a FEN goes in;
what comes back has been checked twice — once for whether the board was read
correctly, once by the engine — and states its own strength. A forced mate is
called a forced mate; an advantage that merely survives the defender's best try
is called that and no more.

Two things distinguish it from wrapping an engine in a shell command:

- **It finishes in seconds.** The search stops on convergence rather than on the
  clock, so a typical position resolves in **2–10 s** instead of the minutes an
  open-ended `go depth 40` costs.
- **It looks for mate on purpose, and says what was proved.** A mate in six and
  an evaluation of +6 are different claims, and an ordinary search will return
  the second in place of the first: iterative deepening prunes a sacrificial
  mating move as unpromising. So every position first goes through a ladder of
  short mate-only searches, and a mate that is found is reported as a mate with
  its distance rather than as a large number. Every run then ends in a verdict
  line that separates *the win is forced, every reply loses* (every reply mated)
  from *every reply is decisive by evaluation* (an opinion, which a fortress
  shares) and from *the win is not forced; these replies hold*.

The ladder is a correctness fix rather than a refinement, and it is on by
default. It costs about 1.7 s on the majority of positions, where it finds
nothing; most of what it is worth comes from the hash table it leaves behind for
the main search rather than from its own hits. The flags that lengthen or remove
it are under [Flags worth knowing](#flags-worth-knowing), the measurements under
[Limitations](#limitations).

After the one-time setup nothing here needs the network. Engine, recognizer and
search all run locally.

This page is written for someone who will run the scripts. For a chess player who
only wants to show the assistant a position and read the answer, start with
**[readme_for_nontechs.md](readme_for_nontechs.md)** — same skill, no shell.

---

## Install

Drop the directory into your skills folder — `~/.claude/skills/chess-verdict`
for Claude Code, or upload the archive in the Claude app under
**Settings → Capabilities → Skills**.

The skill installs its own dependencies on first use:

```bash
apt-get install -y stockfish
pip install chess --break-system-packages --use-pep517
apt-get install -y librsvg2-bin
```

About fifteen seconds together. The engine path can be overridden with
`$STOCKFISH`; it defaults to `/usr/games/stockfish`.

The third line is optional and recommended: it rasterises the diagram to PNG,
which is the form an assistant reading the output can actually open and check.
`pip install cairosvg` serves the same purpose and is used if that is what the
machine has. Without either, the diagram is written as an SVG and nothing else
changes.

**Only if a diagram image has to be recognized automatically:**

```bash
pip install onnxruntime pillow numpy --break-system-packages
```

About 54 MB and a few seconds. The model itself ships with the skill, 1.3 MB
of it, in `scripts/vendor/fenshot/`. It is optional by design: reading the
diagram directly is usually faster, and the recognizer serves as a cross-check
rather than the primary path.

---

## Usage

Normally you do not call the scripts yourself — you show the agent a position and
it runs the pipeline. Invoked directly, one command does everything:

```bash
python3 scripts/solve.py "Rb3rk1/6pp/8/2Q5/6b1/8/1q3PPP/4R1K1 w - - 0 1"
```

```
Position is legal. White to move. Legal moves: 50
Halfmove clock: 0 of 100. The fifty-move counter is assumed to have just reset -- if this position came from a game, check the real count.
Board to verify: https://lichess.org/analysis/Rb3rk1/6pp/8/2Q5/6b1/8/1q3PPP/4R1K1_w_-_-_0_1

Position as read, rendered from White's side -- open this diagram, compare it against the original, and show it to the user before trusting the answer:
  /mnt/user-data/outputs/board.png
Material: White Qx1 Rx2 Px3 -- Black Qx1 Rx1 Bx2 Px2

Best move: Qc4+   evaluation +3.74   (depth 17, 0.4 s)
Second best: Rxb8   +0.03   (depth 17)   lead +3.71 (in chances +0.59)
Main line: 1. Qc4+ Kh8 2. Ra2 Bxh2+ 3. Kxh2 Qb8+ 4. Kg1 Bf5 5. Qd4 Rg8 6. Ra7 Qd8

All opponent replies (3):
  Kh8               +3.74 [d16] 2. Ra2 Bxh2+ 3. Kxh2 Qb8+ 4. Kg1 Bf5 5. Qd4 Rg8 6. Ra7 Qc8 7. Qe5 Bg6
  Be6               +4.67 [d16] 2. Qxe6+ Kh8 3. Ra2 Qb7 4. Rae2 h6 5. Qe7 Qxe7 6. Rxe7 Bd6 7. Re8 Rxe8
  Rf7           mate in 1 [d2] 2. Re8#
Verdict: the win is not forced; these replies hold: Kh8.

Search time: 2.2 s of a 30 s budget
```

That block is one run, not a fixture. The search stops on convergence and the
time it gets depends on the machine, so the evaluation moves by a few hundredths
between invocations — three runs of the above gave `+3.55`, `+3.74` and, under
`--nodes 3000000`, `+3.39` at depth 25. The move, its uniqueness and the verdict
do not move. Quote a number from a doc only with the depth it came from, and use
`--nodes` when a figure has to be reproducible.

Four things in that output are the point of the skill:

**The rendered diagram and the material counts** come before anything else,
because reading the position is the step most likely to be wrong and the one
nothing downstream catches. The board is drawn on every run through `chess.svg`,
which ships inside `python-chess` and costs no install, and rasterised to PNG
when `rsvg-convert` or `cairosvg` is available. Shown in the answer it sits in
the same view as the original it came from, so comparing them needs no click.
The Lichess link is there for replaying the line.

Two text renderings preceded it and both were about fonts. A boxed grid of chess
glyphs was the default in 2.6.0 and was removed in 2.7.0 — it aligns in a
monospace terminal and skews almost everywhere else, and a verification aid that
looks broken stops being read. Plain letters replaced it and survive any font;
2.8.0 renders a board instead, which needs no font at all. 2.9.0 makes that a
PNG where it can, for a reason that has nothing to do with looks: an assistant
reading this output can open a PNG and cannot open an SVG, so the PNG is what
lets the position be checked by machine as well as by eye. The letter grid is
still there behind `--diagram none`, for a plain-text surface where a file path
is worth less than a grid, and it prints by itself if the file cannot be
written.

The per-side counts stay in every mode. They catch a piece read in the wrong
colour or dropped from the reading altogether, neither of which disturbs
legality, and the second of those is invisible on a rendered board as much as in
a grid of letters.

**`lead +3.71 (in chances +0.59)`** is the gap to the second-best move, measured
on a scale where it means something. Thirty centipawns decide the game at
equality and are noise at +7.00, so the two evaluations are converted with the
Lichess sigmoid and the difference is only called a *lead* above 0.05 chances.
Here the solution is unique, and that is a claim the run earned.

**Every reply was scored, not sampled.** With three legal answers the full
enumeration costs nothing, so it ran automatically.

**The verdict line is honest.** `Rf7` is mated and `Be6` loses the bishop, but
`Kh8` holds — White wins a piece, not the game by force. Contrast a position
where it does go through:

```
Verdict: the win is forced, every reply loses (2).
```

### Other question types

```bash
python3 scripts/solve.py "<fen>" --quick          # evaluation only, no defences
python3 scripts/solve.py "<fen>" --timing         # per-stage breakdown
python3 scripts/solve.py "<fen>" --scan full      # enumerate every reply
```

"Who stands better" is `--quick` plus the plans; "was that a mistake" is two
`--quick` runs, before and after. Since 2.10.0 `--quick` keeps the mate ladder,
so neither run is mate-blind; `--fast` is the old behaviour and drops the ladder
too — on a 16-position `matetrack` sample that is 2 mates found against 10 to 12.

### From a diagram image

```bash
python3 scripts/img2fen.py board.jpg b            # b = Black to move
python3 scripts/img2fen.py board.jpg --view black # diagram drawn from Black's side
python3 scripts/img2fen.py board.jpg --timing     # where the time went
```

The reader locates the board itself, so a frame, a caption or a whole page around
the diagram is not a problem and there is no margin ladder to tune. A reading
whose least certain square scores below `0.75` is withheld rather than returned,
because a misread piece leaves a legal position and the error has no symptom
downstream. Unlike the network used through 2.17.0, the gate now covers an
unfamiliar piece set too: that network answered such sets confidently and wrong,
where this classifier drops to 0.46 and is refused. The gate is still a filter on
how sure the classifier was and never a proof that it was right, so the per-side
material count printed by `solve.py` stays part of the check. `--confidence 0`
turns the gate off.

`--view black` matters more than it looks. A Black-view diagram read as a normal
one gives the true position rotated 180° — legal, ordinary-looking, and
completely wrong, with every square carrying the wrong name. Nothing downstream
catches it, so the skill settles orientation from the coordinate labels before
reading a single piece.

If the recognizer fails or cannot be installed, two browser tools read diagrams
well: [fenshot](https://fenshot.com/), which runs entirely client-side and
uploads nothing, and [Chessputzer](https://www.ocf.berkeley.edu/~abhishek/putz),
good on book diagrams.

---

## Flags worth knowing

| Flag | Default | What it does |
|---|---|---|
| `--time` | 5 s | Soft ceiling on the main search; the normal exit is convergence |
| `--min-depth` | 18 | Depth before which stopping is not considered |
| `--stable` | 5 | Iterations the best move must hold before the run ends |
| `--defences` | 4 | How many best defences to show |
| `--scan` | `auto` | `full` enumerates every reply; `off` skips defences |
| `--full-max` | 8 | Replies below this count are enumerated automatically |
| `--win` | 400 cp | Decisive-advantage threshold: past it, deeper search cannot help |
| `--budget` | 30 s | Overall backstop for the whole analysis |
| `--quick` | — | Evaluation only; the mate ladder still runs |
| `--fast` | — | Evaluation only **and** the ladder off — not for sharp positions |
| `--fifty-probe` | `auto` | Re-check the evaluation with the halfmove clock at 90 |
| `--playout N` | — | Play the position out against itself; report the first clock reset |
| `--view auto\|white\|black` | auto | Side the diagram, letter grid and Lichess link are drawn from; pass the source image's side |
| `--nodes N` | — | Reproducible mode for testing the skill, not for answering |
| `--diagram` | `auto` | `png`, `svg`, or `none` for the letter grid |
| `--text-board` | — | Print the letter grid as well as the diagram |
| `--diagram-path` | outputs, cwd or tmp | Where the diagram is written |

Defaults are tuned for a single-core container and need no flags. If a run is
taking minutes, something is wrong with how it was invoked, not with the
position — `SKILL.md` has a section listing the specific invocations that cause
it.

---

## Layout

```
chess-verdict/
├── SKILL.md                        the instructions the agent follows
├── README.md                       this file
├── readme_for_nontechs.md          the same skill, for someone who won't run it
├── FAQ.md                          comparison with chess-best-move
├── CHANGELOG.md                    what changed, and what was verified
├── references/
│   ├── reading-diagrams.md         reading a diagram into FEN by hand
│   ├── timing.md                   the timing journal
│   ├── rationale.md                the evidence behind the rules in SKILL.md
│   └── testing.md                  the suites and the matetrack baseline
├── tests/
│   ├── positions.tsv               the regression set, with expectations
│   ├── hard.epd                    engine blind spots, checked by hand
│   ├── test_stage.py               the timing journal's start/stop behaviour
│   ├── test_compare.py             the board detector, on synthetic diagrams
│   └── test_verdict.py             the reporting rule, on constructed tables
└── scripts/
    ├── solve.py                    search, mate ladder, gap, verdict
    ├── img2fen.py                  diagram → FEN, with orientation handling
    ├── reader_eval.py              the reader, measured across piece sets
    ├── vendor/fenshot/             the ONNX tile classifier and its port
    ├── compare.py                  source diagram and reading, side by side
    ├── stage.py                    timing journal for the whole chain
    ├── selftest.py                 regression suite over tests/positions.tsv
    └── epdcheck.py                 bulk runner for external EPD suites
```

`stage.py` exists because the engine is almost never what makes an analysis slow.
In a measured run the actual search was 1.7 s out of 34.4 s total; installs, the
diagram reading and the assistant's own composing time were the rest. Tuning
engine flags would have improved nothing, and there is no way to know that
without measuring. The table is recorded on every run and printed only on
request.

The window it measures is bounded at both ends: `--start` opens it, `--stop`
closes it after the last command. Without the closing mark the span ran to the
moment the table was printed — and since printing only happens when someone asks,
that billed the user's own reading time to the analysis. One real session
reported 549 s, 97% of it in the `other` row, for fifteen seconds of work.

---

## How is this different from `chess-best-move`?

Briefly: [`chess-best-move`](https://github.com/letta-ai/skills) is a methodology
document about reading boards out of images and formatting the answer to a spec;
this is a pipeline with the engine policy in code. Run on the same position, both
returned `Qc4+` — one after ~1.7 s of engine time, the other after ~11.5 minutes
across five cold engine launches. This skill also reports how strong the
resulting claim is allowed to be, which the other does not attempt; that skill's
per-square vision procedure is the more explicit of the two. (`chess-best-move`
was removed from `letta-ai/skills` in March 2026.)

**[Full comparison, including where `chess-best-move` is the better choice → FAQ.md](FAQ.md)**

---

## Limitations

Three of these are the engine's, not the pipeline's, and no flag reaches them.
`SKILL.md` has the section that says how to recognise them.

- **Fortresses are evaluated as if they could be converted.** On the Penrose
  position the run reports `-11.25` for a side that cannot make progress: played
  out against itself, 98 plies pass with no capture and no pawn move, two short
  of a fifty-move draw. The fifty-move probe and `--playout` make this visible;
  they do not fix the number. The probe is also one-sided — a won rook ending
  fails it exactly as a fortress does, which is why its note stops short of
  calling anything a draw.
- **No tablebases.** K+B+N against a bare king is a forced mate in at most 33 and
  reads `+2.68` at depth 22, `+2.57` at depth 30. Below eight pieces, name the
  ending rather than quoting the number, and use
  `https://tablebase.lichess.ovh/standard?fen=…` for the exact answer — from a
  browser, since the container's egress proxy refuses that host.
- **The fifth FEN field is part of the position.** The same endgame evaluates
  `+2.57` with `0` in the halfmove field and `0.00` with `90`. Diagrams carry no
  clock and `img2fen.py` writes `0` unconditionally, along with `-` for castling
  rights.
- The convergence stop is tuned for tactics. Quiet and endgame positions drift
  with depth; raise `--time` and `--min-depth` together and name the depth the
  number came from. Depth is not always enough: on
  `8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w` the headline reads `+2.67` while the
  reply list in the same output already shows one defence being mated, and the
  position is a forced mate in 10. Where the two disagree, the reply list is the
  one that proved something.
- The mate ladder costs about 1.7 s on every position where it finds nothing,
  which is most of them. That is the price of not reporting a composed mate as
  an ordinary evaluation; `--mate-probe 0` removes both.
- A mate reported by the ladder is proved to exist at that distance or shorter.
  Minimality is not claimed: no descent below the first rung that answers.
- `--defences 4` is a sample. It supports the claim that the advantage survives
  the defender's best try, not that every defence was refuted — only the full
  enumeration supports that.
- The second-best move is reported with its evaluation, not with the line that
  refutes it.
- The recognizer needs a flat 2D diagram and is unreliable on photographs of
  physical boards taken at an angle. It can also read a piece in the wrong
  colour, which passes every legality check — count material per side against the
  diagram.
- Reading a diagram by hand fails most often as a *file shift*: a run of empty
  squares miscounted by one moves a piece sideways, and the result is a legal,
  cleanly parsing FEN. Nothing in the string can catch it, so the skill reads
  every diagram twice in different traversal orders and compares. That is a
  discipline, not a guarantee.
- The scripts assume a Linux environment with `apt` and `pip`.

---

## Changelog

**[CHANGELOG.md](CHANGELOG.md)** — what changed in each release, what was
verified against the files rather than remembered, and what is knowingly missing
from this build.

---

## Licence

**GPL-3.0-or-later** ([LICENSE](LICENSE)).

Copyright (C) 2026 Pavel Kurochka, <https://github.com/PavelKurochka>. The
notice is repeated at the head of every script, which is where the licence
itself asks for it; `LICENSE` is the verbatim GPL text and has no field for a
name.

The choice is not free. `solve.py` imports `python-chess`, which is
GPL-3.0-or-later, and a program that imports a GPL library is a derivative work
of it once distributed. Stockfish is GPL too but is not a dependency in the same
sense: it is launched as a separate process over UCI and no part of it is
included here, so it imposes nothing on this repository.

Third-party material included in the tree:

| What | Where | Licence |
|---|---|---|
| `chess-tiles-v2.onnx`, and the port of the board detector | `scripts/vendor/fenshot/` | MIT, © 2026 SORTINO LABS S.R.L. (`scoriiu/fenshot`) |
| the detector algorithm the above descends from | same, via that port | MIT, © 2016 Sameer Ansari (`Elucidation/tensorflow_chessbot`) |

MIT is compatible with the GPL, and both notices are kept in
`scripts/vendor/fenshot/LICENSE`.

Not included, and fetched or installed separately: Stockfish (GPL-3.0-or-later),
`python-chess` (GPL-3.0-or-later), `onnxruntime` (MIT), `Pillow` (MIT-CMU),
`numpy` (BSD-3-Clause), `librsvg` (LGPL-2.1-or-later), and the `matetrack`
suite, which `SKILL.md` downloads by URL and pins by hash rather than vendoring.

