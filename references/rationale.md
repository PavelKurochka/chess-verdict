# Why the rules are what they are

`SKILL.md` states the rules. This file holds what they were derived from: the
positions, the measurements, and the approaches that were tried and did not
work. The split exists because the rules are read on every activation and the
evidence is read once, when someone wants to change a rule — and 40 KB of
justification loaded to solve a puzzle is 40 KB spent on nobody.

Read this before changing a rule in `SKILL.md`. Do not read it to apply one.
Measurements were taken on one core with Stockfish 16 and are there to be
re-run, not believed. `CHANGELOG.md` has the same material arranged by release;
this file arranges it by rule.

## Where the engine is the weak link

**The fortress.** On `8/p7/kpP5/qrp1b3/rpP2b2/pP2b3/P7/K7 w` Black is a queen,
two rooks and three bishops up, and the run reports `-11.25`. Played out engine
against engine with Black given ten times the thinking time, 98 plies pass with
no capture and no pawn move — two plies short of a draw by the fifty-move rule,
position unchanged. That is not an imprecise number, it is the wrong result, and
quoting it as "Black is winning by eleven pawns" is the worst answer this skill
can give.

A blocked structure is not by itself the trigger. On
`k7/8/1p1p1p1p/pPpPpPpP/P1P1P1P1/8/8/1K1Q4 w` — sixteen locked pawns and an
extra queen — the engine finds mate in 11 in under a second, because the queen
reaches the dark squares on the fourth rank and the chain falls.

**No tablebases.** `8/8/8/8/8/2k5/8/KBN5 w` is a forced mate in at most 33; the
run says `+2.68` at depth 22 and `+2.57` at depth 30, which the reporting rule in
step 4 would turn into "White is about two and a half pawns better". The engine
converts the position in self-play — in 42 moves rather than 33 — so it wins it
without knowing it is won.

**The halfmove clock.** The same placement with `90` in the fifth field
evaluates `0.00` instead of `+2.57`, because the engine applies the fifty-move
rule inside its search and ten plies is not enough to mate.

### The 50-move probe

Measured, three seconds a cell, at `hm = 0 | 50 | 90`:

| position | truth | | | |
|---|---|---|---|---|
| `8/p7/kpP5/qrp1b3/rpP2b2/pP2b3/P7/K7 w` | draw, fortress | −11.25 | −7.98 | 0.00 |
| `8/8/8/8/8/2k5/8/KBN5 w` | mate in ≤33 | +2.64 | +1.80 | 0.00 |
| `1K1k4/1P6/8/8/8/8/r7/2R5 w` | **won, Lucena** | **+8.08** | **+7.02** | **0.00** |
| `r5k1/pp3ppp/8/8/8/5N2/PP3PPP/3R2K1 w` | won, a rook up | +5.43 | +5.27 | +5.36 |
| `k7/8/1p1p1p1p/pPpPpPpP/P1P1P1P1/8/8/1K1Q4 w` | mate in 11 | #11 | #11 | #11 |

**The Lucena row is why the probe is one-sided.** A textbook won rook ending
collapses to `0.00` at `hm = 90` for exactly the same reason a fortress does:
building the bridge takes six moves and the engine only has ten plies. Nothing
in the number distinguishes the two. That is why a collapse is never reported as
a draw.

**A collapsed probe does not outrank a full enumeration.** The session that
added this rule had `Verdict: the win is forced, every reply loses` and *either a
fortress, or a win long enough that the fifty-move rule decides it* four lines
apart in one output, and believed the collapsed probe. The position was a win of
about thirty moves. The script now prints a different note in that case, so the
conflict does not reach the reader as two contradictory lines.

## Reading the files of this skill

Measured on claude.ai, 2026-08-31, one session, four conditions: the *Loaded
skill chess-verdict* line appears only for `view` on a path under `/mnt/skills`.
`bash` reading the same path, `cp -r` of the whole directory, and `view` of a
copy outside `/mnt/skills` each produce nothing. The interface may change;
re-run the four conditions before trusting this over what the transcript
actually shows.

## The recognizer

**How the board is found.** Gradient profiles across the image, arithmetic
sequences of peaks for the grid lines, checkerboard correlation to choose
between candidates. The 2.17.0 margin ladder and its `--all` and `--no-grid`
flags are gone, along with the crop percentages the output used to print. A
grid locked onto a slight offset is handled inside the same pass: the peak
search can lock onto an offset grid when the board texture itself is edge-rich —
a hatched book diagram puts more gradient energy inside the squares than on the
lines — so the reader classifies both the raw box and a grid-snapped one and
keeps whichever the classifier is more confident about, **by mean rather than
weakest square**, because one square spoiled by a move arrow should not settle
which alignment of the board is right. A page holding more than one board-like
region is handled by masking the region just read and scanning again, up to
three times, when the reading comes back with no kings on it.

**Why the confidence gate means something now.** The network used through 2.17.0
had no way to say "I do not know": on a piece set it was never trained on it
returned wrong positions at a softmax of 1.000, so no threshold could have
filtered them. The current classifier drops its confidence on an unfamiliar set
instead — 0.46 on lichess `horsey`, against a floor of 0.70. Measured on the
twenty-piece-set stand (`scripts/reader_eval.py`), 2.18.0 reads 200 of 200
correctly with no silent wrong answers, where the old network managed 89
correct, 46 silent wrong and 65 refusals. **Silent wrong answers are the failure
class that matters**; refusals are recoverable.

**Why the floor moved to 0.75 in 2.24.0.** It was 0.70, upstream's figure,
calibrated against `sharp` where this port uses Pillow — the same fixture scores
0.893 there and 0.764 here — and carried over unmeasured because the piece-set
stand never fired the gate at all. The first local measurement came from a
round trip that needs no network: render sixteen positions from
`tests/positions.tsv` through `chess.svg`, rasterise at fifteen widths from 130
to 760 px, read the PNG back with `img2fen.py`, compare against the FEN it came
from. 240 runs, 16 s, deterministic.

At 0.70: 209 correct accepted, 20 refused, 10 wrong but loud, and **one wrong
and silent** — `7Q/8/8/8/6p1/5pPb/5PpP/2k3K1` at 150 px, read as
`8/8/8/5p2/4pPb1/4PpP1/1k3K2/8`. The grid had locked one square off, so the
white queen on h8 fell outside it altogether; what came back was legal, carried
a king a side, and drew no warning from anything. At 0.75 that reading is
refused and four of the 209 go with it. 0.80 costs eight, 0.85 costs
twenty-three, and neither buys anything the material count does not already
catch.

**The gate does not cover offset grids; it clipped one.** Every wrong square in
that reading was classified confidently — mean 0.93, weakest 0.73 — because a
square off by one is still a square, and the classifier has no view of the grid.
What catches an offset grid is `is_plausible()`, the legality check, and the
comparison sheet. Moving the floor bought a margin on one instance, not a rule.

A real recalibration still needs `reader_eval.py --dataset koryakin
--confidence`, and that still needs network access the container does not have.

**2.25.0: the cause behind the silent misread, and why the floor was the wrong
lever.** The reading above was a box one square off on *both* axes. The
detector's `repair_parity` exists for exactly this kind of error, but its
checkerboard score changes sign on a one-tile shift along one axis only; a shift
along both flips the parity twice and stays positive, and the repair tries only
the four one-axis moves in any case. On that render the found box scored 1268
and read wrong at 0.73; the box one square up-left scored 1753 and read right at
0.90.

On a held-out set — 30 random positions, three board themes, ten sizes, 900
renders — the 0.75 floor still let one silent misread through, at 0.82, so no
floor under 0.82 would have stopped it. Every misread in that set, flagged or
silent, came from a box running past the image edge (41 of 900). Retrying those
boxes one square across, ranked by checkerboard correlation: 821 → 846 correct,
26 → 0 flagged-wrong, 1 → 0 silent. Ranking by the classifier's mean confidence
instead made it worse — 1 silent became 2 on the selection set — because a grid
off by a square classifies its tiles confidently. The floor stays at 0.75; it is
no longer what the silent case rests on.

**Confidence first, legality as a property.** Until 2.16.0 the reader discarded
a correct reading of an illegal position and walked on until some later crop
produced a placement that happened to be legal — legal precisely because a piece
had been misread. Selecting by confidence and reporting legality separately
moved a synthetic benchmark from 42/120 to 120/120. Illegal positions are not
evidence of a misread, and not all illegality stops the analysis.

**Castling rights.** The unconditional `-` written through 2.17.0 was worth 0.1
to 0.3 pawns in the opening positions measured, and the whole answer where
castling is the solution.

## Never type a FEN for a position further down a line

In the run that added `--line`, the assistant wanted a black pawn on g2 to
recapture backwards on h3. Pawns do not capture backwards. The FEN it typed was
`STATUS_VALID`, the engine answered `+0.00`, and a forced win that this same
script had already printed as *the win is forced, every reply loses* was reported
to the user as a fortress draw. Two more hand-typed FENs in the same session
dropped a pawn and invented one; both were legal, both were analysed, and
nothing anywhere said a word.

The same session cost twenty-odd cold-start invocations to reach positions
`--line` reaches in one.

## Legality is a weak check

In the run that prompted the "re-read, do not patch" rule, an `OPPOSITE_CHECK`
was patched by moving a king one file, and three further shifted pieces survived
into the answer — each of which changed the solution. A shift on one rank is
evidence that the same miscounting habit ran on the other seven, which is why
the rule is about the whole position rather than the square that failed. Since
2.22.0 the same reasoning is printed by `solve.py` itself when a FEN will not
parse at all.

## The mate ladder

**What it is worth.** Measured on a 16-position `matetrack` sample: 10 to 12
mates found with the ladder against 2 without it — the range is load on the
machine, since the rungs are timed. With `--mate-probe 0` on the 24-position
reference sample, 5 of 24 against 14.

**Most of that comes from the hash table, not the rungs.** On
`k7/Bp6/1P6/6p1/8/8/6K1/7N w` the ladder reports *no mate up to 5* and the run
then finds mate in 13 anyway, while with `--mate-probe 0` the same run stops at
`Nf2 +8.96` and stays there even at ten times the time. The mate searches leave
forced lines in the shared table, and the ordinary search afterwards reads mate
scores out of it instead of re-deriving them past its own convergence stop. So
`--probe-step` matters far more than the `--mate-probe` ceiling on an
underresolved position, and the ladder should not be judged by whether a
position's mate is within five moves.

**Why the first ladder is cheap and the re-probe is not.** At 0.3 s a rung, a
rung that ran out of time reads exactly like a rung that proved absence. On
`8/1Np1nN2/r3p1p1/p1Q5/3pkb2/B1R2pnK/3p4/5B2 w`, `go mate 4` needs more than
0.3 s and the ordinary search prunes the quiet king move that starts it, so the
run reported `Bd3+ mate in 6` and the mate in 4 was never seen. One slow rung
downward from the mate that was found corrects this.

**Ascending re-probe was tried and rejected.** On a suite weighted to mate in
7–10 it spends five rungs disproving mates in 1 to 5, which was never the
question: 212 s against 70 s on the pinned sample, converting nothing.
Descending, the usual outcome is one failed rung — 14/24 mates found either way,
but 12 at the published distance or shorter against 8, for 107 s against 70 s.

**When the source announces the distance.** On a 16-position `matetrack` sample
the defaults report a plain evaluation on four; re-asked at the published
distance with 3-second rungs, two of the four convert —
`8/2p5/2P5/1RP2p2/p1P5/rnBNpP2/b1PpP3/1k1K4 w` from nothing to mate in 14, and
`rnb5/3p4/q1p1P1K1/3N3B/2P1kpR1/1P3Nb1/2P1ppP1/1r6 w` from nothing to mate in
11, the published distance. The other two stay missed at every setting tried.

**`--quick` and `--fast`.** Until 2.10.0 `--quick` switched off the ladder along
with the second line, so the flag `SKILL.md` recommended for "was this move a
mistake" was the one that misses composed mates. Since 2.10.0 `--quick` keeps the
ladder and the old behaviour lives under `--fast`, which announces itself and
refuses to be combined with `--mate-probe` rather than ignoring it.

**A ladder line has no depth.** `probe_mate` stored `2n` and printed it beside
measured depths until 2.22.0. Substituting the depth the engine reports was
considered and rejected: `go mate 4` comes back at depth 45 on a mate found in
0.3 s, because the search keeps iterating until the movetime is up. The brackets
now name the ladder instead.

## The comparison sheet

**Why the rendering is grey and the source is not.** Desaturating both halves
was tried first, and on a diagram whose last move was highlighted in green the
highlight became an ordinary dark square, with nothing on the sheet to say it
had been dropped. The source is the evidence — process the rendering, never the
original.

**Why grey rather than a matching brown.** 2.20.0 added grey as an opt-in flag
on the argument that paired brown is right when the source happens to be brown
too. A session on a brown wooden-texture screenshot — the best case for that
argument — showed it does not hold: the two palettes are never actually the
same, only adjacent, and adjacent reads as *these should match*, so the mismatch
becomes a thing to explain rather than a thing to ignore. Grey has no answer to
"which brown", so the question does not come up.

**Why the detector has two paths.** The saturation filter exists because
anti-aliased grey text around (200,200,200) lands within tolerance of a light
tan, and the box then grows to swallow the coordinate margin. It also deleted
every unsaturated board: measured on one position rendered twice, the coloured
board has 0.772 of its pixels saturated and crops correctly, the grey one has
0.000 and cropped to nothing. *Tried and wrong:* skipping the filter when it
would empty the mask — on a monochrome diagram the light squares and the paper
quantise into the same colour bin, so the labels come back and the box grows to
the whole image. *What works:* falling back to the darker of the two dominant
colours, because the dark squares are the one part of such a diagram that cannot
be confused with paper and their bounding box is the board's — a1 and h8 are
dark on every board, drawn from either side.

**Why not a board in text.** The boxed grid tried in 2.6.0 arrived visibly
skewed, and a verification aid that looks broken does not get looked at, which
costs exactly the check it existed to provide. 2.7.0 fell back to plain letters,
which survive any font; 2.8.0 renders the board instead, which depends on no
font at all.

## The verdict

**2.27.0: a list of centipawns is not a proof.** The full enumeration used to
call the win forced when every reply scored at `--win` or more. On the fortress
in `tests/hard.epd`, played on by 1.Kb1, that gave "the win is forced, every
reply loses (4)" at +10.71 for a position that is a draw: Black's heavy pieces
are walled in behind their own pawns, the three bishops all run on dark
squares, and every White pawn stands on a light one. The 50-move probe
collapsed to 0.00 and was told, in the same output, that it did not weigh
against a proof. The playout then stopped on a claimable repetition at ply 14
and was reported as cut short by the budget. Three signals, all pointing at the
draw, all suppressed or mislabelled. Now only mates — or a mate in the headline
— are a proof, and the playout says why it stopped.

**A full enumeration outranks the assistant's own analysis.** In the session that
added this rule the script printed `Verdict: the win is forced, every reply loses`
in its first run; the assistant spent the next twenty runs constructing the
position "after the recapture" by hand, using a capture that pawns cannot make,
and told the user the position was a draw. The enumeration is a proof and the
thing contradicting it is not.

2.27.0 narrows that sentence to proofs. On `7k/8/8/8/6p1/4QpPb/5PpP/6K1 w`, the
queen-and-pawns position the `--line` rows in `tests/positions.tsv` are built on,
the enumeration is one reply at +4.41 in centipawns, so it now reads as an
evaluation, and the probe still collapses. What settles it is the playout:
first reset at ply 53 (`Qxh3`), "progress is real" — while the fortress above
ends on a claimable repetition with no reset. Ply 53 of 60 is also why a playout
that runs out of plies without a reset now says so and asks for 100 instead of
reading as a fortress.

**When most of the reply list is mated and the headline is not.** On
`8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w` one run prints
`Best move: Rf1   evaluation +2.67`, a reply of `a5   mate in 7` three lines
below it, and then `Verdict: the win is not forced`. The position is a forced
mate in 10. A defence that is mated proves the position mates at least down that
branch; a headline in centipawns only means the search did not resolve the
others, and the verdict line is derived from the same unresolved search and
inherits the same error.

Settings do not fix it: `--min-depth 24 --time 20` gives `+2.73`,
`--mate-probe 12` gives `+5.70`, and `go mate 8`, `10` and `12` at twenty
seconds each all return a centipawn score. Say the position is mating and that
the distance is not established.

**The trigger is deliberately narrow.** A single losing reply that gets mated is
ordinary and still reads `the win is not forced`, which is correct. Two or more
mated replies outnumbering the ones that hold, while the headline stays a
centipawn score, is an unresolved search rather than a defence holding. Since
2.13.0 the rule also fires on the full-enumeration path, where the condition
previously required a reply that holds and so could never fire in the case it
was written for — a position where *every* reply loses and only the toughest one
is unresolved. That case gets its own, weaker line: the win is forced and only
the distance is open.

## Timing

**Why the journal has to be stopped.** Until 2.11.0 the span ran from `--start`
to the moment the table was printed, and since the table is printed only when
someone asks for it, the wait for that request was counted as part of the
analysis. A four-second analysis followed by a nine-minute pause reported nine
minutes, 97% of it in the `other` row, and every real measurement was rounded to
0%.

**Why the offer exists at all.** The journal cannot be started retroactively,
which is why it runs always — and the same arrangement means the user has no way
of discovering it. A rule that only says *do not print* leaves the feature
unreachable: recorded on every analysis, offered on none.

**Why the wrapper must not be piped.** A run that pipes `stage.py` into a parser
destroys a completed analysis and buys nothing: it costs a second search, and
`cat` on the saved file arrives inside the same harness envelope, which reads as
confirmation that the script emits JSON. On a mate-in-13 position that false
trail cost a repeated 2.8 s search and two wrong diagnoses before
`grep -c json scripts/stage.py` settled it.

## Version discipline

A fixed build that never reached the installed copy is how this skill silently
lost a mate-detection fix for a week, with no symptom until the same position
came back and the same wrong answer with it. The number is declared in three
places and `selftest.py` requires them to agree.

It is deliberately not repeated in the prose of `SKILL.md`: a second copy there
went stale for two releases without anything noticing, which is the same failure
one level up. `stray_versions()` in `selftest.py` therefore works the other way
round from the three-site check — it finds anything that claims to be the
version anywhere in the documentation, this file included, and requires it to
be. Historical references are the normal way these files talk and are fine;
only a bare declaration is a claim about the present.

## Moved from SKILL.md in 2.29.0

The paragraphs below are the reasons behind rules `SKILL.md` still states, moved
here verbatim when the file was cut back to its instructions. `SKILL.md` is
loaded in full on every activation; these are read when a rule is changed.

### Setup

**The third line is worth its three seconds.** `librsvg2-bin` turns the diagram `solve.py` writes from an SVG into a PNG, and the point is not that it looks better: an assistant can open a PNG and cannot open an SVG, so the PNG is what lets the position be checked against the source by machine as well as by the user. `pip install cairosvg` does the same job. Without either, `solve.py` writes an SVG and everything else works unchanged. ImageMagick does not count — it delegates SVG to `rsvg-convert` and fails outright without it.

### What the search does, and why

* **A mate ladder runs before the main search.** `go mate n` for n = 1 up to `--mate-probe` (default 5), `--probe-step` seconds a rung (default 0.3). A correctness fix, not an optimisation. The ladder climbs, so the first rung that answers gives the shortest mate it can see. When it hits, the main search is capped at depth 2n+2, and if the main search still fails to report the mate, **the ladder's line is used instead**: the ladder is a proof and the search is a heuristic. A line that came from the ladder says so in place of a depth, because it has none. The price is about 1.7 s on a position with no short mate. **A ladder the budget stops names the last rung it proved instead of the ceiling it was given** — “no mate up to 5” and “one rung of five ran” are different findings, and a missed mate inverts the verdict rather than blunting it.

* **Once a mate in m is in hand, one slow rung asks whether anything shorter exists.** `go mate m-1` at `--reprobe-step` (default 3 s), descending again only if it hits. The first ladder is deliberately cheap, and at 0.3 s a rung a rung that ran out of time reads exactly like a rung that proved absence. **Ask downward from m, never upward from 1** — the ascending version was tried and is the obvious mistake. The move the main search preferred is kept as the runner-up rather than discarded.

* **A score of +20 or more with no mate gets one direct mate query** (since 2.30.0). `go mate N` at `--deep-mate` (default 30) for `--deep-mate-time` (default 3 s), only when the main search has ended at 2000 cp or more and reported no mate. The ladder never reaches a long mate and the re-probe needs a mate in hand, so a long mate the main search scored as a number had no path to the answer. On `7Q/8/8/8/6p1/5pPb/5PpP/2k3K1 w`, a mate in 17, Stockfish 19's main search mostly runs to its depth ceiling in under a second and stops at +62 to +92 — in a direct trace of eight searches, one reported the mate — while `go mate 25` found it 18 times in 18 in 0.4–2.4 s. With the query the mate in 17 came back in 47 of 48 `solve.py` runs, against three of six before; the re-probe shortens whatever the query finds (18, 19, 21, 23, 25 → 17). The one miss printed the not-a-proof note. A 6 s query, `go mate 25` and a cleared hash for the query did no better (3, 2 and 4 misses in 15 each). A query that finds nothing is reported as not a proof: at 3 s, running out of time and there being no mate within N look the same. Raising `--depth` instead did not help: 2 misses in 6 at 40, 3 in 6 at 50.

* **Most of what the ladder is worth comes from the hash table, not the rungs.** The mate searches leave forced lines in the shared table, and the ordinary search afterwards reads mate scores out of it instead of re-deriving them past its own convergence stop. So do not judge the ladder by whether a position's mate is within five moves. ([Measured](#the-mate-ladder).)

* **The search stops when it converges.** Iterations are read as they arrive; the run ends once the best move has held for `--stable` iterations past `--min-depth`, or as soon as a mate is proven. `--time` (default 5 s) is a soft ceiling on top of that, not the normal exit.

* **The second-best move comes from the same search** (`MultiPV=2`), so both numbers share a depth and the gap between them means something; `--no-second` drops it and roughly halves the main search. The gap is judged on the winning-chances scale rather than in centipawns — thirty centipawns decide the game at equality and are noise at +7.00 — using Lichess's sigmoid, with `lead` reserved for a difference above 0.05 chances. Mates get their own label instead of a number.

* **Defences come from one search after the best move**, with `MultiPV` set to `--defences` (default 4). *The evaluation of the position after the best move already assumes the defender's best reply.* Scoring all thirty legal replies one by one does not make the verdict stronger — it re-derives the same number thirty times. The reply list exists to explain the win, not to establish it.

* **All replies are enumerated only when there are few of them** (`--full-max`, default 8) or when a mate has been found. In a mating net the defender usually has two or three moves, the full list costs under a second, and then the list itself is the proof. Force it anywhere with `--scan full`.

* **The hash table is deliberately small** (64 MB per core): Stockfish zeroes it when a search starts, and on a gigabyte that costs about three seconds of dead time per run. **`--budget` (30 s) is a backstop, not a target.**

### Confirming the reading

The board is found by colour: the two square colours are the most common pixels on any 2D diagram. A monochrome diagram — a scanned book page, a grey theme — takes a second path, where the dark squares alone are used. Where neither holds — a photograph of a physical board, most often — the script refuses rather than cropping to nonsense, shows the source whole, and prints a note saying the grids may not line up. `--no-crop` forces that behaviour, and `--flipped` is for a diagram drawn from Black's side.

**Do not imitate a board in text.** Box-drawing characters and glyphs like `♞` only line up when the font gives both the same advance width, which usually fails outside a monospace terminal — and a verification aid that looks broken does not get looked at, which costs exactly the check it existed to provide. This applies just as much to a board the assistant draws by hand: show the rendered file.

Whether to *stop and wait* for the user is a judgement, and both errors are real. Never stopping is how four shifted pieces reached a confident answer. Stopping every time is worse than it looks: a confirmation that fires on every position and is right most of the time trains the user to wave it through, at which point it costs a round trip and catches nothing. So:

### Timing

**But say the table exists, when the run was slow enough that it might matter.** A rule that only says *do not print* leaves the feature unreachable: recorded on every analysis, offered on none. So close a slow answer with one short line — *"I can show where the time went, if that's useful"* — when an install was needed, when the user was left waiting, or when the budget warning fired. Not after a quick answer, and never the table itself.

The remainder row is itself split, one line per gap, each named after the command it sat in front of. Those lines are where the answer to *why was that slow* usually is, and they need reading rather than repeating: a large gap in front of a command is either a step with no command of its own that was never bracketed — the diagram read by hand, most often — or the assistant composing between tool calls. The table cannot tell the two apart. Say which it was. `references/timing.md` has the mechanics.
