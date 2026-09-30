# Changelog

The version in this file's top entry, in `SKILL.md`'s frontmatter and in
`VERSION` in `scripts/solve.py` must agree. `python3 scripts/solve.py --version`
prints it, so a session can say at a glance which build is mounted. This is not
bookkeeping for its own sake: a fixed build that never reached the installed copy
is how this skill silently lost a mate-detection fix for a week, with no symptom
until the same position came back and the same wrong answer with it.

Measurements quoted below were taken on one core with Stockfish 16 and are there
to be re-run, not believed. Where a change was tried and did not pay, it is
recorded as such rather than quietly dropped — writing it down is what stops the
same idea being re-derived from scratch in six months.

---

## 2.31.0 — 2026-09-30

**The tablebase is asked, not just linked.** At seven pieces or fewer
`solve.py` now queries `tablebase.lichess.ovh` itself and prints the exact
result right after the board link — won, drawn, lost, cursed win or blessed
loss, DTZ, DTM as a mate distance, and the best moves with each one's outcome
for the side playing it — and repeats the verdict as the last line of the run,
where it cannot be lost under the engine numbers. On K+B+N vs K the run now
says `won`, DTM 59 plies (mate in 30), next to the engine's `+2.6`; with the
halfmove clock at 45 it says cursed win and names the clock.

The query needs the host on the sandbox allowlist, which is the user's
setting: *Domain allowlist → Additional allowed domains* in the Claude app.
README (*Exact endgames*), SKILL.md, FAQ and the non-technical readme say so,
and name exactly one host — `tablebase.lichess.ovh`, not `lichess.org` and
not a wildcard. Without it the run says the allowlist refused the host and
which setting lifts that, then carries on exactly as 2.30.0 did. A timeout,
a 429 or an outage is reported as a failure of the day and does not send the
user to the settings. `--tablebase off` skips the query. Six seconds is the
ceiling on the request; four positions came back in 0.45–0.7 s from a cloud sandbox.

`tests/test_tablebase.py` checks the refused/failed split offline, with
stand-ins for `urlopen`, and the report on answers recorded from the service;
`--live` adds one real query and prints SKIP when the host is not allowed.

`SKILL.md` stays under 40 KB: 40 551 bytes. The first draft was 42 442 and
failed the size check in CI; the new text was cut to the rules, the meaning of
DTM, DTZ, cursed and blessed results and the JSON address moved to
`references/rationale.md`, and the timing and reference sections were
tightened without dropping a rule.

### Also in this release

**Three endgames with tablebase truth in `tests/hard.epd`.** Until now every
row there had a truth from analysis or a published problem; these three are
checked against the Lichess tablebase (2026-09-27). K+N+N vs K+P
(`8/4K3/N7/2N1p3/8/8/8/4k3 w`) is won with a DTM of 93 plies while the engine
says about +1.2; K+B+B vs K+N (`8/8/2nB4/8/8/4k3/4B3/5K2 w`) is a cursed win,
DTZ 119, so a draw under the fifty-move rule; and the K+B+N row repeated with
the halfmove clock at 45 is a cursed win too, DTZ 59 plus 45. On the two
drawn ones `solve.py` shows about +1 and says nothing of the rule; only the
tablebase link does, which is what the rows check. Found by sampling random
five-man positions and keeping those where Stockfish and the tablebase
disagreed or the DTZ ran past 50; one clear disagreement in 64 random
positions, four in 60 from the long-ending classes.

---

## 2.30.0 — 2026-09-26

**A huge score with no mate gets one direct mate query** (issue #3). On the
queen sacrifice in `tests/positions.tsv` (`7Q/8/8/8/6p1/5pPb/5PpP/2k3K1 w`, a
mate in 17) Stockfish 19's main search often reported +62 to +92 instead of the
mate — three misses in six runs of 2.29.2 on one machine. A per-depth trace of
eight bare searches showed where: most reached the depth ceiling of 30 in under
a second with no mate, and only two would have been stopped by the convergence
rule, so the hypothesis in the issue was half right. Raising the ceiling did
not help (2 misses in 6 at `--depth 40`, 3 in 6 at 50). Asked `go mate 25`
directly, the engine found the mate 18 times in 18, in 0.4–2.4 s.

So when the main search ends at +20.00 or more and reports no mate,
`solve.py` now asks once: `go mate 30` for 3 s (`--deep-mate N`,
`--deep-mate-time SEC`; `--deep-mate 0` turns it off; skipped under `--fast`
and `--nodes`). A mate it finds replaces the score and says so, and the
existing re-probe then shortens it — the query returned 18, 19 and 23, the
re-probe 17 each time. A query that finds nothing prints that it is not a
proof. On Stockfish 19 the mate in 17 came back in 47 of 48 runs — 18 run
alone, 30 inside `selftest.py`'s own harness after the row before it — and
the one miss printed that note, not a false claim. It is fewer misses, not
none. Three variants did no better on 15 runs each and were dropped: 6 s for
the query (3 misses), `go mate 25` (2), a cleared hash for the query (4).
`selftest.py` on Stockfish 19, full runs: 25 of 25 twice before the `_fill_pv`
change below; after it, 24 of 25 (this row) and then 25 of 25. The timed runs
took 85–87 s.
Positions below +20 pay nothing.

**`_fill_pv` has a clock.** It lengthens a mate line that came back truncated
with a search to depth 2n+2, and had no time limit; harmless for the ladder's
mates of 1 to 5, open-ended for the mates of 17 to 30 the new query and the
re-probe hand it (depth 36 to 62). It now stops after 2 s or at the end of the
budget and keeps the short line. The six `--timing` runs after the change
reported the same 20-ply main line as before. The timing table names the new
step `mate-only search up to 30, 3.0 s: mate in 18 found`.

`tests/test_ladder.py` covers the query and the clock with scripted engines;
`SKILL.md` gains one line and is 39,940 bytes; the measurement is in
`references/rationale.md`.

**The "one mated reply and one that holds" row no longer depends on the engine
version** (issue #2). After 1.Qc4+ in `Rb3rk1/6pp/8/2Q5/6b1/8/1q3PPP/4R1K1 w`
the row needs Kh8 to hold, and with the default `--win 400` that rested on a
live score about half a pawn from the threshold: under 4.00 on Stockfish 16,
+4.56 to +4.94 on Stockfish 19, where the verdict correctly became "decisive by
evaluation" and the row failed. It now runs with `--win 600`. Three runs on
Stockfish 19 all said "the win is not forced", Kh8 holding with a margin of at
least a pawn; Be6 scores +5.69 to +6.02 and sometimes holds too, which does not
change the verdict. The rule itself stays covered engine-free in
`tests/test_verdict.py`. Test-only; with it and the query above, the suite
passes in full on both Stockfish 16 and 19.

## 2.29.3 — 2026-09-26

**A dead engine is reported, not crashed on or blamed on the clock** (issue #1).
Stockfish 19 exits on a position it calls unsupported — nine white pawns,
`4k3/8/8/8/P7/PPPPPPPP/8/4K3 w`, is the row in `tests/positions.tsv` that
showed it — after printing `CRITICAL ERROR: ... Reason: Unsupported position.
WHITE has more than 8 pawns.` Stockfish 16, which CI installs, analyses it.
With Stockfish 19, 2.29.2 did three wrong things:

- the mate ladder caught the engine's death as an ordinary `EngineError` and
  printed "stopped … because the budget ran out" one second into thirty, with
  advice to raise `--budget` that reproduces the crash;
- the main search, which catches nothing, ended in a traceback, and closing the
  dead engine printed a second one;
- Stockfish's own reason never reached the user: python-chess sees only a dead
  process.

`EngineTerminatedError` is a subclass of `EngineError`, which is how five
handlers in `Session` absorbed it. Each now re-raises it. `run()` catches it,
asks a fresh engine process for its reason (`engine_refusal()`, a second or
less) and stops with `STOCKFISH STOPPED ON THIS POSITION`, the reason, and the
instruction not to give a verdict the engine never computed. `SKILL.md` carries
the same rule in one paragraph beside the python-chess one; it is 39.9 KB.

**`selftest.py` accepts alternatives, `A || B`**, for this row only: the
analysis on engines that take the position, the clean refusal on those that do
not. The 2.29.2 traceback satisfies neither. `tests/test_ladder.py` drives every
`Session` method with an engine that is already dead: all six checks fail on the
2.29.2 code and pass now.

Measured on Windows with Stockfish 19: the nine-pawn row passes, in 1.9 s, and
`engine_refusal()` returns the reason in 0.37 s. The suite is 23 or 24 of 25.
One failure is issue #2, a row whose verdict sits half a pawn from `--win` and
moves with the engine version. The other comes and goes: the queen sacrifice on
h3 (`7Q/8/8/8/6p1/5pPb/5PpP/2k3K1 w`, mate in 17) is sometimes returned as
+65 to +92 instead of the mate. It is not this change — six runs each, the
2.29.2 code missed the mate three times and this one once, a difference too
small to credit — and CI on Stockfish 16 has not missed it.

## 2.29.2 — 2026-09-26

Repository housekeeping; nothing in `SKILL.md` or the scripts changed except the
version number.

**`chess-best-move` is marked as removed.** `FAQ.md` and `README.md` compare
this skill with `chess-best-move` from `letta-ai/skills`, which was removed from
that repository in March 2026 (commit `6017653`). The comparison stays, with a
note saying so; the links point to where it used to live.

**Tests run on GitHub Actions.** `tests.yml` runs every file in `tests/`, the
three-way version check and the description limits on each push and pull
request. `selftest.py` runs there too but does not fail the build: it searches
against a clock, and a shared runner is not the machine its baseline was
measured on. Its first run there passed 25 of 25 in 52 s.

**Releases are built by `release.yml`.** A `vX.Y.Z` tag that matches `VERSION`
runs the tests, builds `chess-verdict.zip` from the tagged tree — a
`chess-verdict/` folder, executable bits kept, repository-only files left out —
and attaches it to the release. A hand-run build from `main` matched the
published 2.29.1 archive file for file and mode for mode; only the two documents
above differed.

## 2.29.1 — 2026-09-21

Pre-publication fixes; no change in what the scripts compute.

**The frontmatter conforms to the Agent Skills spec.** The skill-creator
validator rejected it: `Unexpected key(s) in SKILL.md frontmatter: version`.
The declaration moved to `metadata.version`, and `license: GPL-3.0-or-later`
was added beside it, matching the headers. `selftest.py` reads the version from
the new place, so the three-way agreement check still holds.

**`.gitignore` is back.** The mounted copy had lost it — dotfiles did not
survive the upload — and every build since 2.25.0 shipped without it. Restored
verbatim from the 2.23.0 tree.

**Scripts carry the executable bit**, so `./scripts/solve.py` runs from a
checkout as the shebang lines intend.

**`README.md` lists `--view`** in the solve.py flag table.

## 2.29.0 — 2026-09-21

**`SKILL.md` is back under 40 KB: 44.5 → 39.6 KB.** It is loaded in full on
every activation, and it had grown by 4.5 KB since 2.23.0 cut it to 40 — much of
that from 2.24–2.28, each fix bringing its own paragraph of justification. The
rules stay; fourteen paragraphs of reasons moved verbatim to a new section of
`references/rationale.md`, "Moved from SKILL.md in 2.29.0": why the ladder
climbs and the re-probe descends, what the hash table contributes, how the
comparison sheet finds the board, why a text board is not drawn, why stopping
to confirm is a judgement, how to read the timing gaps. Two duplicated rules
were merged rather than moved — the halfmove clock was explained twice, and the
offer of the timing table was made in two places with two wordings.

**The tablebase link is for a person.** `solve.py` printed
`http://tablebase.lichess.ovh/standard?fen=…` as "the exact answer", which is a
JSON document. It now points the user to the Lichess link it already prints,
whose analysis board shows the tablebase in its explorer panel, and gives the
API as the same data in JSON, over https. Checked: the API answers with
`category`, `dtz`, `dtm` and a `moves` list (`win`, 59, 59 and 14 moves for
`8/8/8/4k3/8/8/8/4KBN1 w`). A readable per-move table at syzygy-tables.info was
considered and not linked: its bot protection refused the check, so the URL
format could not be verified.

**One pre-existing broken anchor.** `references/testing.md` sent readers to
`rationale.md#the-suites`, a heading that does not exist; the text it meant is
in `testing.md` itself, and the link now points there. Every relative link and
anchor in the tree resolves.

## 2.28.0 — 2026-09-21

**The main search keeps a mate it finds.** `search()` stops as soon as line 1
reports a mate at a depth of at least twice its length. Stockfish sends the
MultiPV lines of an iteration in order, so at that moment line 2 of the same
depth has not arrived, and the rule that a depth counts only in full fell back
to the depth before — discarding the mate. Recorded from the engine on
`r1bq1rk1/pp1n1p1p/5P2/1B3p2/3B3b/PR6/2PQ2PP/3K3R w`: depth 12 `+8.92`, depth 12
line 2 `+2.12`, depth 13 `mate in 6`; returned: depth 12, `+8.92`. With
`--mate-probe 0` the run printed `Rg3+ +9.96 (depth 12)`. Line 1 is now taken
from the mating depth, line 2 keeps its own.

The ladder and the re-probe hid this in default runs: on the pinned matetrack
sample of 24 the fix changes nothing with default settings (15 of 24 either
way) and turns 5 into 6 with `--mate-probe 0`. So the figure `testing.md` gives
for what the ladder is worth was measured against a search that threw some of
its own mates away, and overstated the ladder by one position in 24.

**The diagram can face the way the source does.** `solve.py` drew the board from
the side to move, with no way to change it. A book prints White at the bottom
whoever is to move, so a Black-to-move book diagram came out rotated 180°
against its source, and the check in step 4 was made across the rotation.
`--view white|black` now sets the side for the diagram, the letter grid and the
Lichess link; `auto`, the default, keeps the old behaviour. `compare.py`
accepts the same `--view`, beside its `--flipped`.

**One Lucena figure instead of three.** `SKILL.md` said the playout first resets
the clock at ply 9, `testing.md` at ply 19, `tests/hard.epd` inside ten plies.
Three runs gave 18, 19 and 14: self-play at 0.3 s a move is not deterministic,
and the `hard.epd` expectation failed every time. All three now give the
measured range.

**`proved by a mate-only search`** replaces `proved by the mate ladder` beside a
line from `go mate n`. The re-probe also produces such lines and runs under
`--mate-probe 0`, where the old wording claimed a ladder that had been switched
off.

**Tests.** `tests/test_ladder.py` plays a recorded info stream into `search()`
and checks the mate survives; `tests/positions.tsv` gains `--mate-probe 0` on
the same position end to end, and a `--view white` row.

## 2.27.0 — 2026-09-21

**The full enumeration no longer calls an evaluation a proof.** On the fortress
in `tests/hard.epd` (truth: draw), played on by 1.Kb1 with `--line`, the run
printed "Verdict: the win is forced, every reply loses (4)" at +10.71. "Loses"
meant scored at `--win` (400 cp) or more at depth 16 — an opinion, and exactly
the opinion a fortress produces. Worse, the collapsed 50-move probe was told in
the same output that it did not weigh against "a proof", and `SKILL.md` told the
assistant the line outranked both the probe and its own reasoning.

`Verdict: the win is forced` is now printed only when every reply is mated or
ends the game, or when the headline itself is a mate. A list that is decisive
only in centipawns prints `every reply is decisive by evaluation (n), the
weakest at … -- an evaluation, not a proof`, the probe's ordinary collapsed note
follows it, and `SKILL.md` says to weigh the two against each other and let
`--playout` decide. Positions whose replies are all mated behave as before.

**The playout says why it stopped.** A playout that ended on a claimable draw —
the fortress above, a repetition at ply 14 inside a 60 s budget — printed
"stopped … because the budget ran out -- raise --budget … before drawing a
conclusion". The loop broke on `is_game_over(claim_draw=True)`; the note only
checked that fewer plies had run than were asked for and that the game was not
formally over. `playout()` now returns a `reason` (`ended`, `budget`, `error`,
`done`), and the budget note appears only when the budget did it. A claimable
draw with no reset of the clock is the fortress signature, and `SKILL.md` says
so next to the rule that a truncated playout proves nothing.

**The verdict rule is tested directly.** `tests/test_verdict.py` carried a copy
of the enumeration branch and tested the copy, which passes whatever the
original does. The branch is now `enumeration_verdict()`, a pure function in
`solve.py`, and the tests call it; the playout's note logic is
`playout_notes()`, tested in `tests/test_ladder.py` with a scripted engine that
repeats the position. `tests/positions.tsv` gains the fortress row end to end.

**A playout that runs out of plies no longer reads as a fortress.** With a
centipawn list now settled by the playout, its limit matters. On
`7k/8/8/8/6p1/4QpPb/5PpP/6K1 w`, a win of about thirty moves, the first reset
came at ply 53 of the default 60 — a slower run would have printed "Nothing was
converted, which is what a fortress looks like" about a win. A run that uses up
its plies with no reset and no repetition now says it has seen nothing yet and
asks for `--playout 100`, the fifty-move rule's own horizon; at 100 it says the
rule would have ended the game.

## 2.26.0 — 2026-09-21

The four items 2.25.0 left open, and one latent crash.

**The python-chess install line carries `--use-pep517`.** python-chess 1.11.2
is published as source only (the last wheel is 1.10.0), so pip builds it on the
spot, and on images whose Debian setuptools is patched for system installs the
build dies with `AttributeError: install_layout`. Reproduced on a Python 3.11
container; the Python 3.12 one used for 2.24.0 did not show it. `--use-pep517`
builds in an isolated environment with setuptools from PyPI and installs in
1.4 s; on images where the old line worked it changes nothing. `uv pip install
--system` works too, but is not guaranteed to exist where the skill runs, so it
is not the documented line.

**A missing python-chess is a sentence, not a traceback.** `solve.py`,
`img2fen.py` and `compare.py` imported it bare. Each now stops with the install
command and the reason for the flag. `SKILL.md` said "the engine part works
regardless" of a failed install, which was true of the recognizer's runtime and
false of python-chess; it now says which is which, and that a failed
python-chess install means saying so rather than analysing by hand as if the
engine had.

**`references/reading-diagrams.md` agrees with the rest of the skill.** It
called `-` "the safe default" for castling, while `img2fen.py` reads rights off
the home squares — so the two readings step 2 compares disagreed on every
position with king and rooks at home, without any misread behind it. The hand
rule is now the machine's rule. It said the halfmove clock "affects nothing
except fifty-move counting", against the section of `SKILL.md` built on the
same K+B+N ending reading `+2.57` or `0.00` by that field alone; it now says the
`0` is an assumption. And it rested the orientation rule on "diagrams are drawn
from the point of view of the side to move", which books do not follow; the
premise is now the one that holds — nobody turns a board for the side that is
waiting — with the converse stated as false. The same premise is corrected in
`SKILL.md`.

**The 400 px sentence is replaced by the measurement.** It said a diagram below
roughly 400 px "ends in a refusal rather than a wrong FEN". On python-chess's own
piece set renders read correctly down to about 140 px and are refused below;
the sentence now says that, and says book sets are unmeasured.

**`gap_note()` no longer raises on lines out of order.** A mated best line over
an unmated second fell through to centipawn arithmetic on a mate score and
raised `TypeError`. Stockfish sorts its lines, so this should be unreachable,
which is why it is a label saying so rather than a silent reorder. Covered in
`tests/test_verdict.py`.

## 2.25.0 — 2026-09-21

Two fixes in the recognizer, both for a silent wrong answer. The first also
corrects a claim 2.24.0 made.

**A board one square off on both axes is now found and moved back.** 2.24.0
raised the confidence floor to 0.75 on the strength of one silent misread and
said the floor had removed it. On 900 renders the rule had never seen — 30
random positions, three board themes, ten sizes — 0.75 still let one through, at
a weakest square of 0.82. The floor was clipping instances of the failure, not
stopping it.

The cause is in the detector. `repair_parity` fixes a box one tile off by
watching the checkerboard score change sign, but a shift along both axes flips
the parity twice and the score stays positive; the repair also only tries the
four one-axis moves. Such a box does leave a mark: it hangs off the image
(23..162 on a 150 px canvas in the original case). `img2fen.scan_once()` now
retries a box like that one square across in each of eight directions and keeps
the best by checkerboard correlation. Boxes that fit the image are untouched.
The vendored detector is not modified.

| | correct | refused | wrong, flagged | wrong, silent |
|---|---|---|---|---|
| held-out 900, 2.24.0 | 821 | 52 | 26 | 1 |
| held-out 900, 2.25.0 | 846 | 54 | 0 | 0 |
| selection 255, 2.24.0 | 219 | 36 | 0 | 0 |
| selection 255, 2.25.0 | 230 | 25 | 0 | 0 |

**Tried and rejected: ranking the neighbours by mean confidence**, which is how
`scan_once` already chooses between the raw and the grid-snapped box. A grid
off by a square classifies its tiles confidently, and on the selection set that
ranking turned one silent misread into two.

**`img2fen.py` no longer fills in White to move.** Without the second argument
a normal-view reading printed `w` in the FEN with no line saying so. That FEN
then passed the side-to-move check `solve.py` gained in 2.24.0 — the guess had
simply moved one step up the chain. On the Black-to-move tactic in
`tests/positions.tsv` the read gave `Nxe2 +7.79` for White instead of
`Rxg3+ +7.44` for Black, both plausible. Now the normal view prints one FEN per
side and a line saying the turn was not read, unless a king in check settles it,
in which case it says which and why. `--view black` still defaults to Black,
with the line it always printed: a flipped board is a real sign, a normal one is
not, since books print White at the bottom whoever is to move.

**Tests.** `tests/test_reader.py` is new, the first offline cover of the
recognizer. Fixed cases: the 150 px render, a normal render left alone, both
side-to-move branches. `--sweep` reruns the held-out figure above with its seed.

**Still open.** The setup line `pip install chess` fails on images whose Debian
setuptools rejects legacy builds (`AttributeError: install_layout`);
`--use-pep517` fixes it. `solve.py` still dies with a traceback when
python-chess is missing. `references/reading-diagrams.md` still calls `-` the
safe castling default and says the halfmove clock affects nothing, against the
rest of the skill. The 400 px sentence in `SKILL.md` is still wrong.

## 2.24.0 — 2026-09-08

Four fixes, all of the same kind: a place where the skill stated something it
had not established. Three came out of a critical read of the code, the fourth
out of the first local measurement of the recognizer's confidence gate.

**The mate ladder no longer reports absence it did not prove.** `probe_mate()`
leaves its loop when the budget runs out, and the caller printed
`no mate up to N` regardless of how many rungs had actually run. Measured by
substituting a counting stub for `engine.analyse`: `--budget 5 --mate-probe 16
--probe-step 3` on `8/8/8/4k3/8/8/8/R3K3 w` ran **one** rung and wrote
"mate ladder: 16 rung(s) of 3.0 s, no mate up to 16" into the timing table and
the shared journal. `probe_shorter()` did the same with `nothing shorter than m`
after a loop that never asked a single rung.

This is the confusion the descending re-probe exists to prevent — a rung that
timed out reads exactly like a rung that proved nothing is there — left standing
in the ladder's own account of itself. Both now return how far they got:
`probe_mate()` returns `(n, Line, proved_to)`, where `proved_to` is the highest
rung that came back with a definite negative, and `probe_shorter()` returns
`(n, Line, proved)`. A truncated ladder prints a `NOTE` naming the rungs it
never asked, and its stage line says `absence proved only up to k of N rungs`.
A completed ladder is unchanged and still says `no mate up to N`.

Why this mattered more than it looks: a missing mate does not make an answer
less precise, it inverts it. And the truncation is silent in the ordinary case —
`budget_warn` only fires below one second remaining, so a run that spent its
budget on the ladder and finished with 1.3 s to spare said nothing at all.

**A FEN with no side-to-move field is refused.** `chess.Board("8/8/8/4k3/8/8/8/
4KBN1")` parses and comes back as White to move; `solve.py` printed
"Position is legal. White to move" and analysed it, with the FEN itself absent
from the banner. `SKILL.md` step 1 says the turn must never be inferred, because
a tactic solved for the wrong side is the opposite answer rather than a near
miss — and the one place the turn was being inferred was the script's own input
handling. A placement with fewer than two fields now stops the run. A FEN that
stops after the turn gets a line saying the castling field was filled in as `-`,
which is an assumption in exactly the way the halfmove clock already was.

**`--quick` and `--fast` no longer swallow the defence flags.** `--scan full
--quick` printed `(defence analysis disabled)` and carried on, and the banner
advertised `--defences 6` as a setting in force while the defence analysis was
off — the invented-settings line the banner was written to prevent, produced by
the banner itself. `--scan full`, `--defences`, `--defence-time` and
`--full-max` now raise an argparse error when combined with either flag, on the
same rule already applied to `--mate-probe` with `--fast`: a flag that does
nothing must say so rather than be swallowed. `--scan off --quick` is still
accepted; the two agree.

**The recognizer's confidence floor is 0.75, and for the first time it is a
measured number.** 0.70 came from upstream, calibrated against `sharp`
rasterisation where this port uses Pillow, and had been carried unmeasured
because the twenty-piece-set stand never fired the gate at all.

The measurement that was missing needs no network: render sixteen positions from
`tests/positions.tsv` through `chess.svg`, rasterise at fifteen
widths from 130 to 760 px, read the PNG back and compare. 240 runs, 16 s,
deterministic. At 0.70: 209 correct accepted, 20 refused, 10 wrong but loud, and
one **wrong and silent** — `7Q/8/8/8/6p1/5pPb/5PpP/2k3K1` at 150 px, read as
`8/8/8/5p2/4pPb1/4PpP1/1k3K2/8`, the grid locked one square off with the queen
on h8 outside it. Legal, one king a side, no warning from anything. At 0.75 that
reading is refused and four of the 209 go with it: 2% of accepted readings for
the failure class the whole reader was rebuilt around. A refusal costs a hand
reading; a silent wrong answer costs the verdict.

**Tried and rejected: fixing this in the gate.** The floor cannot cover an
offset grid and did not here — every wrong square in that reading was classified
confidently, mean 0.93, because a square off by one is still a square and the
classifier never sees the grid. 0.75 clipped one instance by three hundredths.
What catches an offset grid is `is_plausible()`, the legality check and the
comparison sheet, and 10 of the 11 wrong readings in the sweep were caught by
exactly those. The floor is the fourth line of defence, not the first, and
raising it further only buys refusals: 0.80 costs eight correct readings, 0.85
costs twenty-three.

**Tests.** `tests/test_ladder.py` is new: twelve checks driving `probe_mate()`
and `probe_shorter()` with a scripted engine that records which rungs it was
asked. A real engine would make the result depend on the machine's load, which
is precisely the variable under test. `tests/positions.tsv` gains two rows, both
refusals, for the FEN field and the flag conflict. `references/testing.md` had
its row count wrong (21 for 20) and one relative link that resolved to
`references/references/rationale.md`; both fixed.

**Still open, and deliberately not touched here.** `SKILL.md` says a diagram
below roughly 400 px "ends in a refusal rather than a wrong FEN". Measured on
the sweep above, correct readings run down to 140 px, refusals start at 120, and
180 px produced a wrong FEN rather than a refusal. Both halves of that sentence
are wrong and it is still in the file.

The round-trip harness that produced the confidence figures is also not in the
tree, so the numbers above cannot yet be re-run from a clean checkout — which is
the one thing this file asks of every measurement it quotes. `tests/test_reader.py`
is the missing piece: the recognizer currently has no offline automated cover of
any kind, and `reader_eval.py`, the only thing that touches it, needs hosts the
container blocks.

---

## 2.23.0 — 2026-09-07

**`SKILL.md` is 40 KB instead of 64 KB, and the evidence behind its rules moved
to `references/`.** Nothing was deleted; two kinds of content were separated.

The file is loaded in full on every activation. Roughly a third of it was
justification — the position a rule was derived from, the measurement that
settled it, the approach tried first and rejected. That material is what stops a
rule being re-litigated from scratch in six months, so it is worth keeping; it
is also read once, by whoever is changing the rule, and paid for on every run
that merely applies it. A session solving a puzzle was carrying about 6000 tokens
of case history it had no use for.

**Two new files.** `references/rationale.md` (17 KB) holds the evidence,
arranged by rule rather than by release, with an anchor for every place
`SKILL.md` points into it: the fortress and Lucena measurements, the
50-move-probe table, the recognizer's confidence history and the 200/200 stand,
the `--line` session that reported a forced win as a draw, the ascending-re-probe
rejection, the hash-table finding, the grey-versus-brown argument, and the
positions the verdict rules were written on. `references/testing.md` (6 KB) holds
the suites, the matetrack baseline and seed, `--nodes`, the hand-check list, and
what each `tests/` file is for — none of which a session answering a position
ever needs.

**What stayed in `SKILL.md`:** every step, every command, every flag, every
prohibition, and a one-clause reason where the reason changes what to do. A rule
whose justification left is still a rule; the link beside it is for the reader
who wants to argue with it.

**Measured:** `SKILL.md` went from 64 165 bytes at 2.22.0 to 40 666 -- about
6000 tokens saved on every activation. Check it with `wc -c SKILL.md`; the
figure has to be the shipped file's, and the first draft of this entry gave
40 448, which was a working copy rather than the release. A changelog whose
numbers do not reproduce against the artifact beside them is worse than one
with no numbers, since it invites the reader to stop checking.
The earlier estimate in review was 20–25 KB, and that was wrong — reaching it
meant cutting rules rather than justification, which is the opposite trade. The
sections that resisted compression are steps 3 and 4, and they resisted for the
right reason: almost every sentence in them is an instruction.

**One test row moved from `positions.tsv` to the hand-check list,** and it is a
loss worth naming. `8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w` was added in 2.22.0 to
cover `v_branch_mates` -- the rule that says a mated reply list outranks a
centipawn headline -- and it does not hold still. Four consecutive runs at
`--scan full`: `2 of the 4 replies are mated`, `the win is not forced`, `3 of
the 4`, `the win is not forced`. The position sits exactly on the `mated > holds`
boundary the rule turns on, and whether `Rxf1+` resolves in the reply budget
decides which side of it the run lands. A row that fails one time in two teaches
the reader to ignore the suite, which costs more than the branch it covers, so
it goes back to the list in `references/testing.md` that is checked by hand. The
branch itself is now covered only by `headline_understates()` in
`test_verdict.py`, which tests the predicate and not which line gets printed. A
deterministic position for it is still wanted.

Related, and not fixed here: `7Q/8/8/8/6p1/5pPb/5PpP/2k3K1 w` (`mate<=25`) failed
once in four full runs of the suite while passing five out of five when run
alone. Standalone it answers `Qxh3` with mate in 17 or 18 in 4.6-7.3 s, so the
row is close enough to the time budget that a loaded machine can push it over.
Flagged rather than loosened: raising the bound would hide the timing, which is
the part worth knowing.

**Two corrections found while splitting.** The instruction to read the skill's
own files named `/mnt/skills/user/chess-verdict/`, a path that does not exist in
the current mount; it now says "the directory `SKILL.md` was opened from", which
cannot go stale. And `stray_versions()` in `selftest.py` now scans
`references/*.md` as well — the check exists because a version number once sat
stale in `SKILL.md`'s prose for two releases, and most of that prose is now in
`references/`, so leaving it unscanned would have re-opened the hole the check
was built to close. A third turned up on the verification pass: the "What no
suite measures" paragraph kept a bare `#where-the-engine-is-the-weak-link` link
after moving into `references/testing.md`, where that anchor no longer exists.
It now points at `../SKILL.md`. Anchors that survive a move are the failure mode
of splitting a file, and `SKILL.md`'s eleven links into `references/` were
checked the same way.

---

## 2.22.0 — 2026-09-07

**Everything here came out of one review pass over the whole tree.** The theme
is the same in every item: the scripts were strict about what they *print* and
much less strict about what they *do* when something goes wrong before the
printing starts.

**A FEN that does not parse, and a Stockfish that is not there, now say so.**
`chess.Board(args.fen)` and `Session()` were the two unguarded calls in
`solve.py`, and both are on the likeliest path in normal use. A miscounted rank
is the most common error there is in a hand-read FEN — the file has a whole
section on it — and it exited with a `ValueError` traceback; a container without
the engine exited with `FileNotFoundError`, which is the very case Setup in
SKILL.md tells the assistant to report in words. Two texts and two `try` blocks.
The FEN message ends by repeating the rule from step 2: re-read the whole
position rather than patch the field that failed, because a miscount on one rank
is evidence the same habit ran on the other seven. The engine message sits after
the diagram and the material counts, so it can say the reading still stands.

`compare.py` already had this check (`try: chess.Board(args.fen)`), which is how
the gap was found: the two scripts disagreed about whether an unparseable FEN
was worth a sentence.

**`compare.py` finds a monochrome board.** The saturation filter added to keep
coordinate labels out of the crop was deleting every unsaturated board with
them, which is to say every scanned book diagram and every grey theme —
precisely the sources this skill is pointed at. Measured on one position
rendered twice: the coloured board has 0.772 of its pixels saturated and crops
to `(25, 25, 615, 615)`; the grey one has 0.000 and cropped to `None`, falling
back to the uncropped image with a warning. The check the sheet exists to
provide was lost exactly where reading is hardest.

*Tried first and wrong:* skip the saturation filter when it would remove most of
the mask. It fails, and the reason is worth keeping. On a monochrome diagram the
light squares and the paper quantise into the same colour bin, so the two
dominant colours are paper and dark squares rather than the two square colours;
without the filter the labels come back and the box grows to the whole image.
Measured on a grey board with grey labels: wanted `(60, 20, 700, 660)`, got
`(0, 0, 720, 720)`.

*What works:* keep the saturation filter as the first path, unchanged, and fall
back to the darker of the two dominant colours when it would empty the mask. The
dark squares are the one part of a monochrome diagram that cannot be confused
with paper, and their bounding box is the board's — a1 and h8 are dark on every
board, drawn from either side. The grey board now crops to
`(24, 24, 616, 616)`, one pixel from the coloured path, and the grey-board-with
-grey-labels case lands within one pixel of ground truth. The coloured path is
bit-for-bit as before. `tests/test_compare.py` gains
`test_monochrome_board_is_found`, built on the same fixture as the grey-label
regression so it exercises both problems at once; the old fixtures used only the
lichess brown, which is why nothing caught this.

**A line off the mate ladder no longer reports a depth it does not have.**
`probe_mate` and `_fill_pv` stored `2n` and `2n+2` in `Line.depth` and printed
them in the same brackets as a measured depth, with nothing to tell the two
apart. Substituting the depth the engine actually reports was considered and
rejected: `go mate 4` comes back at depth 45 on a mate found in 0.3 s, because
the search keeps iterating until the movetime is up, so the honest number
answers a question nobody asked. `Line` grows a `proved` flag and the brackets
now read `(proved by the mate ladder, 4.6 s)`. This is the same objection the
`banner()` docstring makes about invented settings: a figure that reads exactly
like a measurement has to be one.

**The time beside the best move is the engine's, not the main search's.** It was
`dt` from `ses.search`, which excludes the ladder and the re-probe. On
`8/1Np1nN2/r3p1p1/p1Q5/3pkb2/B1R2pnK/3p4/5B2 w` that printed `(depth 7, 0.0 s)`
four lines above `Search time: 4.5 s`, reading as though the answer had been
instant. It is now `time.time() - ses.started`, which covers the ladder, the
main search and the re-probe and differs from engine startup by hundredths.

**`selftest.py` parses both shapes,** or every mate the ladder proves would read
as "no answer line in the output". `epdcheck.py` shares the parser and needed no
change, which is why it shares it.

**`t()` in `img2fen.py` raises on a missing substitution instead of returning the
template.** `t("st_recog")` on `"recognition: {n} pass(es)"` was returning the
string with its braces intact, and that string went into the `--timing` table
*and* into the shared journal, so `stage.py --report` showed
`recognition: {n} pass(es), recognition: 1 pass(es)` to the user. A static scan
of all three scripts found this was the only such call out of 70 templated keys;
the guard is there so the next one fails at the call site rather than in the
output.

**The mate sign in `selftest.parse_output` was blind.** `out["mate"] = -0` was
meant to distinguish mate received from mate delivered, and `-0 == 0` in Python,
so both read as "no mate delivered". A separate `mate_given` key carries it. The
outcome is barely reachable, but a parser blind to the side is the wrong defect
to have in a suite whose sibling, `epdcheck.py`, checks the sign before the
distance on purpose.

**Three rows in `positions.tsv` run `--scan full`.** The suite passes
`--scan off` everywhere else, for the good reason given in its docstring, and
the consequence was that the whole verdict branch — `v_incomplete`,
`v_branch_mates`, `v_holds`, `v_forced`, `v_forced_mates` and the
`forced_verdict` handover to `fifty_note_collapsed_forced` — had no end-to-end
cover at all, only the two helpers beneath it in `test_verdict.py`. The fourth
column already allowed per-row flags, so this needed no new machinery. Cost:
17 rows in 51 s before, 21 rows in 50 s after — a mating net enumerates in
fractions of a second. It paid immediately: the first draft of the mate-in-one
row expected `every reply loses` and failed, because after `Ra8#` there are no
replies and the branch is skipped rather than emptied. The row now checks that.

**Smaller.** `compare.py` removed its temporary SVG on both returns but not when
`subprocess.run` raised anything other than `FileNotFoundError`; it is in a
`finally` now, and the empty PNG placeholder is removed on the no-rasteriser
exit as well.

**Not touched, and why.** The unreachable `MateGiven` branch in
`enumerate_replies` — `board` there is the position after the best move and the
move being pushed is the defender's, so the winner can only ever be the
defender; verified over 4000 random games, where the side that has just moved is
the winner 44 times and the other side never. Excising one branch is easy and
the polarity around it deserves a reading of its own. `all_sequences` in
`fenshot_detect.py` is quadratic in the peak count with a scan of the
accumulated sequences inside it, and has no time bound; it is vendored and
faithfulness to upstream is the point, so any guard belongs outside it.

---

## 2.21.0 — 2026-09-06

**The rendered half of the comparison sheet is grey by default; `--mono` becomes
`--no-mono`.**

2.20.0 added the grey rendering as an opt-in flag and gave the reason it should
be off by default: the paired brown is right when the source happens to be brown
too. A session on a brown wooden-texture screenshot — the best case for that
argument — showed it does not hold. Both halves in brown, the source's own
squares carrying a wood grain and the rendering's flat, the eye still spends its
first pass on which brown is which. The two palettes are never actually the
same; they are only adjacent, which is worse than being obviously different,
because adjacent reads as *these should match* and the mismatch becomes a thing
to explain rather than a thing to ignore.

The sheet asks exactly one question — *is this piece on the same square in both
halves* — and every property of the rendered board that is not shape and
position is noise against it. Grey has no answer to "which brown", so the
question does not come up. Measured on the session's own sheet at
`8/5pk1/6r1/4Q3/1pq5/P7/1P6/K6R b`: nothing about correctness changes either
way, which is the point — the default should be the one that does not invite a
question about the sheet instead of about the position.

**The asymmetry is unchanged and is still the whole design.** Only `render_fen`
takes the colours; the source half is copied through untouched under both
settings. The 2.20.0 note stands and is worth repeating, because a default is
easier to extend carelessly than a flag: desaturating the source as well was
built first, and it silently turned a green last-move highlight on a8/d8 into an
ordinary dark square, with nothing on the sheet to say a highlight had been
dropped. The source is the evidence the reading is checked against. Processing
it can only remove information, and the removal is invisible.

**Why an inverted flag rather than `--mono` kept alongside it.** `--mono` with a
`mono=True` default would be a flag that does nothing, which is how a flag comes
to mean the opposite of what it says two releases later. `--no-mono` names the
one thing it now changes. Anything invoking `compare.py --mono` in a saved
command breaks loudly on an unrecognised argument instead of quietly producing
the same sheet it used to; the flag has been in for five days, so there is no
reason to carry a deprecated alias for it.

`render_fen(fen, path, flipped=False, mono=True)` — the keyword default flipped
with the CLI default, so a caller importing the function gets the same sheet the
script produces. `tests/test_compare.py::test_mono_leaves_the_source_alone` now
asserts the default sheet is grey and that `--no-mono` redraws only the right
half.

---

## 2.20.0 — 2026-09-01

**`compare.py --mono` draws the rendered half in grey.**

The comparison sheet puts the source diagram beside the position as read, and
the two are almost never in the same palette — a brown book diagram against
python-chess's own brown, a blue screenshot against the same brown, a grey
newspaper scan against it again. The sheet asks one question, *is this piece on
the same square in both halves*, and hue is the first thing the eye answers
instead. `--mono` renders the right-hand board on `#f0f0f0` and `#b8b8b8`, which
takes that comparison off the sheet. Off by default: the paired brown is right
when the source happens to be brown too, and a flag that changes the reading
check for everyone should be asked for.

**The source half is never processed, and the first attempt proved why.**
Desaturating both halves was built first and it did look better — perfectly
neutral, nothing but shape and square. It also silently destroyed evidence: the
diagram in hand had its last move highlighted in green on a8 and d8, and in grey
that highlight became an ordinary dark square. Nothing on the sheet said a
highlight had ever been there, and the highlight was what identified the losing
move. The source is the evidence the reading is checked against; processing it
can only remove information, and the removal is invisible. `--mono` therefore
touches `render_fen` and nothing else.

**No behaviour changes without the flag.** `render_fen(..., mono=False)` passes
an empty `colors` dict, which is what `chess.svg.board` already defaulted to, so
every existing sheet is byte-identical.

---

## 2.19.2 — 2026-09-01

**The description is written for a 1024-character limit and displayed in 500.**

The claude.ai skill card renders the first 500 characters of `description` and
stops there — mid-word, with no ellipsis and no indication that anything follows.
At 976 characters the previous text was cut after *a puzzle ("find the*, which is
character 500 exactly; the next characters in the file are *` win", "wh`*. Round
number, no marker, no warning: a rendering width, not a validator.

**Nothing was broken, and that is worth stating plainly.** The full 976
characters reach the model — the text ending *player biographies* was confirmed
present in a session's skill list while the card showed the truncated half. So
triggering was never affected and no position was ever missed because of this.
What was lost is what a human reads in Settings before deciding whether to
enable the skill, which is a smaller thing but not nothing.

**The fix is ordering, not cutting.** The first two sentences — what the skill
does, and the three shapes a position arrives in — now end exactly on character
500, so the visible card ends on a full stop. Everything past the cut is the
material a reader can do without on first contact: positions from a game or a
book, engine-evaluation checks, the non-puzzle questions, the *even if the user
never mentions Stockfish* clause, proof depth, and the negative scope.

Three wordings changed only to land the boundary, and none of them cost a
trigger: *the Stockfish engine* → *Stockfish* in the opening clause, *Use this
skill whenever* → *Use it whenever*, and *how far anything short of mate has
actually been proved* moved out of the first sentence into its own in the tail.
All four puzzle phrasings survive, including `"is there a mate here?"` added in
2.19.1. Net 976 → 954, leaving 70 characters under the spec's cap.

**Rejected: rewriting to fit inside 500 altogether.** The trigger list is the
mechanism by which the skill loads at all, and it is the longest part of the
field. Cutting it to satisfy a display width would trade real triggering
accuracy for the appearance of tidiness in a settings pane. The spec allows
1024, the model receives 1024, and the card is not the consumer that matters.

**`selftest.py` now refuses to run on a bad `description`.** Two checks, in the
same spirit as the version agreement immediately above them. Over 1024 the field
is invalid and at least one loader drops the whole skill during frontmatter
parse — no stderr, no exception, the skill just stops appearing in the list,
which is the exact silent-failure class this suite exists for. Under 1024 but
cut mid-sentence at 500 is not fatal, so it fails the same way: better caught at
build time than noticed in a screenshot two releases later. The run banner now
prints the length alongside the version.

---

## 2.19.1 — 2026-08-31

**The short descriptions name forced mate; the long ones already did.**

The mate ladder had four paragraphs of measurement in `SKILL.md` and none of its
own in either place a reader meets first: the frontmatter `description` and the
two-bullet pitch at the top of `README.md`. Both framed the skill as an engine
evaluation plus a verdict line, which is exactly the reading under which the
ladder looks like a tunable rather than the correctness fix it is.

* **`description`** gains *whether the win is a forced mate and of what length*
  as a stated outcome, and `"is there a mate here?"` as a trigger phrase. The
  outcome clause matters because a mate and a large evaluation are different
  claims and only one of them is a proof; the trigger phrase matters because
  asking for a mate is among the most common ways a concrete position arrives,
  and the list did not cover it.
* **`README.md`** merges the *says what was proved* bullet with the reason the
  ladder exists — an ordinary search prunes a sacrificial mating move and hands
  back a centipawn score in place of the mate — and follows it with the cost and
  the honest note that most of the ladder's value is the hash table it leaves
  behind, not its own hits.

**Deliberately not in `description`: the mechanism.** That field's job is to
decide when the skill is loaded at all, so words spent on how it works are words
not spent on when to use it. The clause added is what comes out, not what runs.

Not measured. A `description` governs triggering, and this build has no harness
for that, so the edit is additive — a clause and a trigger phrase, no rewrite of
what was there — to keep the blast radius small. If triggering regresses on
positions that used to route here, this entry is the place to start.

---

## 2.19.0 — 2026-08-31

**`stage.py --report` splits the `other` row into named gaps.**

The remainder row pooled every unmeasured interval into one number. In a real
session it read `other: 60.0 s, 69%`, and the only conclusion available from it
was that something somewhere was slow — which is not a diagnosis. The same
sixty seconds, attributed:

```
  other: gaps not covered by a measurement                       60.0 s   69%
      before install engine                                       2.2 s
      before install python-chess                                 2.1 s
      before install rasteriser                                   2.2 s
      before install imaging                                      2.7 s
      before reading the diagram (img2fen.py)                    12.2 s
      before solving the position (solve.py)                      7.6 s
      before building the comparison (compare.py)                21.5 s
      before after the second-best move                           7.4 s
      after the last command                                      2.1 s
```

Now the table answers questions. The 12.2 s in front of `img2fen.py` is the
diagram being read by hand, a step `SKILL.md` says to bracket with
`--begin`/`--end` and which that session did not — so the breakdown recovers
unbracketed steps instead of letting them dissolve into the pool. The 21.5 s in
front of `compare.py` is the engine's output being read and thought about, which
is work and should stay. And the four installs carrying 2.1–2.7 s each while the
fifth carries 0.0 s is a natural experiment: the fifth shared a shell invocation
with the fourth, so ≈2.2 s is the cost of a round trip rather than of the work,
and splitting five installs across five commands spends about nine seconds on
nothing.

**Nothing new is recorded.** Every level-0 row has carried both its duration and
its closing timestamp since the format was written; the gap in front of a row is
`end - duration - previous_end`, a subtraction that was simply never done. So
this is a change to `report()` and `read()` only, costs nothing at runtime, and
works on journals written by older builds.

Details worth keeping:

* **Rows with no closing timestamp are stepped over by their duration** rather
  than skipped. Skipping them was the first attempt and it folds their measured
  work into the following gap, which is the exact error the row exists to
  prevent. Only the synthesised orphan row and child-written rows lack the
  field, but the arithmetic has to survive them.
* **Gaps below 0.05 s are dropped, not listed.** On the session above that
  removes exactly one line — the 0.0 s in front of `install recognizer` — and
  the pooled row above still carries the exact total, so nothing is lost. The
  floor matches the one already used to decide whether `other` is printed at
  all.
* **Rejected: printing each gap inline, above the command it precedes.** It puts
  the number closer to what it describes, and it also interleaves unmeasured
  time with measured work in a table whose whole purpose is to separate them.
  Nesting the gaps under `other` uses the same indentation idiom as the internal
  stages under a command, which is what the table already teaches the reader.

`tests/test_stage.py` gains `test_gap_breakdown`: one 1.2 s pause between two
0.2 s commands, asserting the gap is named after the command that *followed* it
and not the one before, and that the listed lines sum to the pooled row. The
fixture concentrates the whole gap in one place on purpose — a gap spread evenly
across several commands passes a misattributing implementation just as happily
as a correct one.

---

## 2.18.5 — 2026-08-31

**`solve.py` and `img2fen.py` print one identifying line before they work, and
`SKILL.md` says to stop opening the skill's own files with `view`.**

The web interface labels an activated skill with its name and nothing else, and
it emits that label once per `view` call on a path under `/mnt/skills` — so a
run that opened `SKILL.md`, a reference file and a script showed three identical
*Loaded skill chess-verdict* lines and no version, no arguments, no subject.

Measured 2026-08-31 in one claude.ai session across four conditions — `view`
and `bash` reads, each against `/mnt/skills` and against a copy under
`/home/claude`: the label is emitted only by `view` on `/mnt/skills`. A `bash`
read of the same file produces none, and neither does `cp -r` of the entire
directory, which rules out per-file accounting. Two remedies followed from that
and both were taken. The label cannot be renamed — it comes from the client and
the frontmatter has no field for it — so the useful information has to come from
where this skill does control the output.

`banner()` lists only settings that differ from their defaults. A full flag dump
was written first and discarded on reading it: forty items hid the one that had
been chosen, which was the entire reason for printing anything. `--engine` and
`--confidence` are pinned in `img2fen.py` and print whether or not they differ,
because those two *are* the reading and a gate whose setting is left to be
assumed is half a gate. The banner is built after the `--fast`/`--mate-probe`
resolution, so a flag that was overridden is not reported as if it held.

Printed from each script's `__main__`, not from `run()`, so importing `solve` as
a library stays silent — `selftest.py` and `reader_eval.py` both do that. The
extra first line was checked against every consumer of the output: `selftest.py`
scans line by line for the `Best move:` line, nothing reads `stdout[0]`, and
`reader_eval.py` calls `img2fen.recognize()` below `main()`.

`img2fen.py` imports `banner` from `solve.py` rather than restating a version of
its own. A fourth declaration site is exactly what `stray_versions()` in
`selftest.py` exists to refuse, and the import path was already there.

## 2.18.4 — 2026-08-29

**The copyright notice the licence asks for, in all ten source files.**

No script behaviour changes.

2.18.2 added `LICENSE` and left the tree without an author. That was not an
oversight to tidy up later: the GPL's own closing section asks for a notice at
the head of each source file naming the year and the holder, and `LICENSE` is
the verbatim text with no field to put one in. Without it the repository states
its terms and not whose terms they are.

Copyright (C) 2026 Pavel Kurochka, `https://github.com/PavelKurochka`.

Stamped below the shebang in the seven scripts and in the three files under
`tests/`; the tests are covered because they are source too, not because
anything downstream reads them. `README.md`'s licence section names the holder
and says why the name is not in `LICENSE`.

`scripts/vendor/fenshot/` is deliberately untouched. It is MIT and belongs to
its authors, and stamping a GPL notice on someone else's file would be a false
claim about who wrote it and under what terms.

Checked after stamping: the module docstrings survive — comments are not
statements, so `"""` after the block is still the module docstring, which
`solve.py` passes to `argparse` for its help text.

---

## 2.18.3 — 2026-08-29

**Removed the `*.epd` rule added to `.gitignore` one release earlier.**

No script behaviour changes.

The rule was written to keep a downloaded `matetrack.epd` out of the tree, with
`!tests/hard.epd` re-admitting the fixture. The case it guards against does not
arise: the only command in the repository that fetches that file, in
`SKILL.md`'s matetrack section, writes to `/tmp/matetrack.epd`. `grep` for a
download into the tree returns that one line and nothing else.

What the rule did cost is real. A new fixture — `tests/endgames.epd`, say — would
have been silently untracked, surviving `git add -A` and `git status` without a
word and going missing at the next clone. Trading a failure that announces
itself (a large file in `git status`) for one that does not is the wrong
direction, and it is the same class of defect as the stale version number that
`stray_versions()` exists to catch.

The remaining rules each cover something observed in this tree:
`__pycache__/`, which `selftest.py` creates on its first import of `solve.py`
and whose `.pyc` files embed the absolute path of the build machine in
`co_filename` — verified, not assumed; the diagram files `solve.py` and
`compare.py` write beside a run when `/mnt/user-data/outputs` does not exist,
which is the normal case for someone running from a clone; and the built
archive.

---

## 2.18.2 — 2026-08-29

**Made the tree publishable: a licence, an ignore file, and a sample output that
matches the build it claims to come from.**

No script behaviour changes.

### The licence was not a free choice

`solve.py` imports `python-chess`, which is GPL-3.0-or-later. A program that
imports a GPL library is a derivative work of it once distributed, so the tree
is now **GPL-3.0-or-later** and carries the full text in `LICENSE`. Publishing
it with no licence at all would have been worse than picking the wrong one:
under GitHub's terms an unlicensed public repository grants no rights beyond
viewing and forking, so nobody could legally install it.

Stockfish is GPL as well and imposes nothing here, which is worth stating
because it looks like the same case and is not: it is launched as a separate
process over UCI, no part of it is included, and the skill would run against any
UCI engine on that path.

The vendored `scripts/vendor/fenshot/` stays MIT and is compatible. Its LICENSE
now carries a second notice — © 2016 Sameer Ansari, `Elucidation/tensorflow_chessbot` —
because the board detector descends from that project through fenshot's
TypeScript port. `vendor/README.md` described that lineage in prose from the
start; the prose is not the notice MIT asks for.

`README.md` gets a licence section listing what is in the tree and what is
merely installed or fetched, so the question can be answered without reading
`SKILL.md`. The `matetrack` suite is in the second list: it is downloaded by URL
and pinned by hash, never vendored, and that stays deliberate.

### The sample output in README.md was from an older build

It reported `+3.56` on the reference position where this build reports `+3.74`,
with a different main line from move 4. Both READMEs now show the same run,
captured from 2.18.2.

That fix exposed a larger one. Three runs of the same position on the same build
gave `+3.55`, `+3.74`, and `+3.39` at depth 25 under `--nodes 3000000`. The
search stops on convergence and the depth it reaches depends on machine load, so
a pasted evaluation is not reproducible and re-pasting a fresh one every release
would be busywork chasing noise. Both files now say so next to the block:
`README.md` names `--nodes` as the reproducible mode, `readme_for_nontechs.md`
says the second decimal is noise and the move and verdict are what hold. The
move, its uniqueness, the reply list and the verdict were identical across all
three runs.

### Also

* `.gitignore`: `__pycache__`, the diagram files `solve.py` and `compare.py`
  write beside a run, the built archive, and `*.epd` with `tests/hard.epd`
  re-admitted — the ignore rule is aimed at a downloaded `matetrack.epd` landing
  in the tree, not at the fixture that belongs there. **The `*.epd` rule was
  removed in 2.18.3: the download it guards against writes to `/tmp`, so it
  protected nothing and would have hidden any new fixture.**

Checked and found clean while going through the tree: no credentials, no
personal paths, no bundled third-party data. The only absolute path in the
scripts is `/mnt/user-data/outputs` as the first candidate for the diagram, with
`cwd` and the temporary directory behind it.

---

## 2.18.1 — 2026-08-29

**A second README, for the reader who will never open a terminal.**

Documentation only; no script behaviour changes.

`README.md` is written for someone who will run the scripts. It opens with an
install block, spends a table on flags and a section on why `stage.py` exists.
For a chess player who only wants to hand the assistant a diagram and read what
comes back, that is the wrong document — not too long, but organised around
decisions they will never make.

Added `readme_for_nontechs.md`:

* what the skill is, in two claims: it checks the board reading before it
  analyses, and it separates *winning* from *proved*;
* installation as the app actually presents it — upload the archive under
  Settings → Capabilities → Skills, then ask in ordinary words;
* one real run, annotated line by line: the diagram and material counts first,
  what `+3.55` means, what `depth 17` means, what the *lead* and *in chances*
  figures answer, and both forms of the verdict line;
* when to distrust the number — fortresses, endings below the tablebase
  boundary, quiet positions — plus the cross-check that when the headline says
  *small advantage* and a listed defence is being mated, the list is the one
  that proved something;
* a short glossary: FEN, evaluation, depth, forced mate, tablebase, fortress.

The sample output in it was captured from a run of this build rather than copied
out of `README.md`. The copy there is from an older build and reports `+3.56`
with a different line from move 4; two documents quoting the same position with
different numbers is a small thing that costs a reader real time. `README.md`'s
copy is left alone here — re-running it belongs with a change to that file, not
to this one.

**The version number is deliberately not stated in the new file.** The first
draft carried a `Current version: 2.18.0` line, which is exactly the defect
`stray_versions()` in `selftest.py` was written to catch — a fourth site that
claims to be the version and that nothing updates. `selftest.py` now scans
`readme_for_nontechs.md` alongside `SKILL.md`, `README.md` and `FAQ.md`, so if
that line ever comes back it fails the suite instead of going stale. The scan
list is still an enumeration of known files and cannot catch a fifth document
nobody registers; a glob over `*.md` was considered and dropped, because
`CHANGELOG.md` is nothing but historical version claims and would have to be
excluded by name anyway.

---

## 2.18.0 — 2026-08-29

TensorFlow is gone. The recognizer is now a 1.29 MB ONNX tile classifier from
`scoriiu/fenshot` (MIT), vendored under `scripts/vendor/fenshot/` together with
a Python port of that project's board detector. `--engine fenshot` is the
default and, for the moment, the only value.

### Why replace it at all

The network used through 2.17.0 could not say "I do not know". Its softmax runs
over the thirteen classes it was trained on, and a piece set outside them is not
a class it can doubt: on `kosal` it returned wrong positions at a softmax of
1.000. That is why the confidence gate never protected against the failure that
mattered — raising it to 0.999 still left seven wrong answers while discarding
sixteen good readings.

Measured on twenty lichess piece sets, ten positions each, both readers on the
same 200 rendered diagrams:

| | correct | **silent wrong** | refused |
|---|---|---|---|
| 2.17.0 (TensorFlow CNN) | 89 | **46** | 65 |
| 2.18.0 (fenshot ONNX) | **200** | **0** | 0 |

Per set, the old network read seven reliably — alpha, cardinal, cburnett,
companion, fresca, merida, tatiana — which matches the 2.14.1 finding of six.
On `chess7` it produced nine wrong readings out of ten with no refusals at all.
The 46 wrong readings contain 203 substituted squares, 4.4 pieces per diagram:
this was systematic incomprehension of a glyph set, not a slip on one square.
The commonest substitutions were rook read as knight (14), a knight seen on an
empty square (12), a pawn vanishing (10).

A representative failure, on `chess7`:

    truth  5k2/4pp2/5bp1/4q2p/3N4/2p1nQ1P/P1P5/K3R3
    read   5k2/4pp2/5bp1/4q2p/3N4/2p1nq1P/P1P5/K3R3

A white queen read as black. Perfectly legal, passes every legality check, and
visible only in the per-side material count — the class of defect step 2 exists
for.

### What else changed with it

**Install cost.** `onnxruntime pillow numpy`, about 54 MB, installs in seconds.
The old stack was `board_to_fen tensorflow-cpu tf-keras`, a few hundred
megabytes, measured at 58 s on a warm mirror and two to four minutes cold, plus
2.05 s of import on every single run. The advice not to install reflexively is
correspondingly softened in SKILL.md: the cost argument is gone, the ordering
argument (read the image first, recognize second) is not.

**The confidence gate means something now.** 0.70, upstream's figure, replacing
0.85. On lichess `horsey` — a set the classifier does not know — it scores 0.46
and is refused, where the old network would have returned a wrong position
confidently. But see the caveat below.

**Castling rights are inferred** from the home squares instead of written as a
constant `-`. SKILL.md priced that constant at 0.1 to 0.3 pawns in the opening
positions measured, and at the whole answer where castling is the solution. The
inference errs one way only: a king that moved and returned is credited with
rights it does not have. The halfmove clock is still a constant `0`, and still a
claim rather than a blank.

**The crop ladder is gone**, and with it `--all` and `--no-grid` and the crop
percentages the output used to print. The new detector finds the board by
gradient profile and does not need margins tried against it. What replaces the
grid pass is a per-scan arbitration: the raw box and a grid-snapped box are both
classified and the more confident wins, by mean confidence rather than weakest
square, so one square spoiled by a move arrow cannot decide the alignment.

**`legality_rank.py` is deleted.** It measured legality-first against
confidence-first crop selection, and the new reader produces one reading per
scan, so there is no selection left to measure. The 2.16.0 result it supported
(120 correct against 42) stands in the record; the script that produced it does
not apply to this reader.

**`reader_eval.py` is back in the distribution.** It was referenced by the
roadmap and was not in the shipped tree — the measurement it performed could not
be reproduced by anyone holding the zip. It now builds the twenty-piece-set
stand from `raw.githubusercontent.com` and scores the reader on it:
`--render` once, then run it. Roughly 15 s for 200 diagrams.

### Tried and did not work

**Calling fenshot as a service.** It runs entirely in the browser and uploads
nothing — that is its stated privacy property — so there is no endpoint to call.
`fenshot.com` is also outside the container's allowlist. Handing the user a link
remains the fallback it always was; it is not an integration.

**Running the npm package under Node.** This works and was measured: 8 of 8 on
the upstream fixture set, 0.55–0.85 s per diagram, 7 s to install. Two things
argued against shipping it. The published `@scoriiu/fenshot@0.1.4` emits
extensionless relative imports in its `dist`, which bundlers resolve and plain
Node ESM does not, so it needs a resolver hook to import at all. And the
published build lags the repository: `grep -c plausible` gives 9 in the sources
and 0 in `dist`, meaning the npm copy has no implausibility check. The Python
port has neither problem and is faster (0.22–0.80 s), because the Node wrapper's
overhead disappears.

**The template bank** planned as `--engine bank` in the 2.16.0 roadmap. It
refuses rather than guesses, which is the right behaviour, but it cannot read a
set it has no glyphs for, and the fenshot classifier covers all twenty sets
outright. The bank remains a possible second engine; the flag is in place for it.

**Calibrating the gate on koryakin.** Still blocked: `kaggle.com` and
`storage.googleapis.com` return `host_not_allowed`, checked again this release.
The dataset is synthetic renders anyway, so it would have measured the easy half
of the problem — the roadmap item promised calibration on real images and the
data under it does not deliver that. Restated accordingly.

### Caveats, stated because they are easy to overlook

**The gate is inherited, not measured on this pipeline.** 0.70 is upstream's
number, calibrated against `sharp` rasterisation; this uses Pillow, and the same
fixture scores 0.893 there against 0.764 here. On the piece-set stand the gate
never fired — all 200 readings cleared it — so there is no local evidence to move
it in either direction. A margin of 0.064 on a real screenshot is not a margin.

**Everything above is rendered diagrams.** Both readers were measured on the
same easy half of the problem. What speaks for photographs is nine fixtures from
the fenshot repository — real screenshots of lichess, chess.com, a reddit page, a
whole screen with two boards, a marble board, a book diagram — where the port
reads 8 of 8 and correctly refuses the ninth. Nine is not two hundred.

**The stand had a defect that produced plausible false numbers.** The first
version of the renderer embedded twelve `<svg>` glyphs into one board document.
Four sets — celtic, fantasy, kosal, spatial — carry a `<style>` block using short
class names like `.st15`, and CSS in SVG is document-wide regardless of nesting,
so the black king's rules overwrote the white king's and the board rendered in
one colour. That run reported 68 silent wrong answers for the new reader and four
sets at zero out of ten. It was caught by looking at one image, not by any check.
The renderer now rasterises each glyph separately, and `reader_eval.py` carries a
`self_check` that compares the two rooks and refuses to build a stand where they
are identical. A fault in the measuring instrument is the worst place to have
one: its output is indistinguishable from a finding.

## 2.17.0 — 2026-08-27

**A position reached by a move that does not exist is still a legal position.**

Asked what happens after a capture, the run that prompted this release did the
obvious thing and the wrong one: it typed the resulting placement into a fresh
FEN and analysed that. The recapture it had in mind was a black pawn on g2
taking *backwards* onto h3. No such move exists. The placement it produced was
nevertheless a perfectly ordinary legal position; `chess.Board(fen).status()`
returned `STATUS_VALID`, the engine evaluated it at `+0.00` without a word, and
a forced win — which the same script had already printed as
`Verdict: the win is forced, every reply loses` at the top of the session — was
reported to the user as a fortress draw. Two other hand-typed FENs in the same
session lost White's g3 pawn and invented a pawn on b2; both were legal, both
were analysed, and neither said anything.

This is not a variant of the errors 2.16.0 dealt with. Those were illegal
positions being mistaken for misreadings. This is the reverse: a position no
legality check can object to, because nothing is wrong with it except that the
game cannot get there from where the user is standing. The only check that
catches it is playing the moves.

* **`solve.py --line "MOVES"`** plays a sequence onto the FEN and analyses what
  it reaches. SAN or UCI; move numbers and result markers are stripped, so a
  line can be pasted as written (`1.Qd4+ Kh7 2.Qf6`). Every move is parsed
  against the board in front of it, and a bad one **stops the run** — naming the
  move, its index, why it failed (unreadable / not legal / ambiguous), the FEN
  at that point, and the moves that *were* available. On the position above:

  ```
  STOPPED AT MOVE 1 OF THE LINE ('g2h3'): not legal here.
    Position at that point: 7k/8/8/8/6p1/5pPQ/5PpP/6K1 b - - 0 1
    Black to move, 3 legal moves: Kg8, Kg7, gxh3
  ```

  The three legal moves are the whole answer: `gxh3` can only be the g4 pawn,
  and the ninety minutes spent evaluating what the g2 pawn does afterwards were
  spent on a position that never arises.

  On success it prints the line in SAN and the FEN reached, with a note saying
  the position was played out rather than typed. That note is not decoration —
  it is the difference the reader needs to see.

  The flag also removes a second cost. Diagnosing side lines by hand meant
  twenty-odd separate `solve.py` invocations, each starting a cold engine with
  an empty hash table, which is exactly what the *What makes this slow* section
  tells the caller not to do. One position, one line, one run.

* **The fifty-move probe no longer argues with a verdict it cannot overturn.**
  The same output carried `Verdict: the win is forced, every reply loses` and,
  four lines below it, `either a fortress, or a win long enough that the
  fifty-move rule decides it` — two statements pointing opposite ways with
  nothing to rank them. They are not equals. A full enumeration in which every
  reply loses is a proof; the probe is a ten-ply search that failed to show
  progress, and it fails that way on a won rook ending too. When the enumeration
  has returned a forced win, the collapsed probe now prints a note that says so
  and points at the second of its own two cases, instead of reopening the first.

  Only the wording changed and only in that combination: the probe still fires
  where it did, and the ordinary collapsed note is untouched.

* **`selftest.py` gained `rejects=`** — the run stops, gives a stated reason, and
  produces no answer line — kept separate from `refuses=`, which additionally
  demands the `ILLEGAL POSITION` wording. Folding the two together would have
  passed a build that had stopped checking moves entirely, since the move case
  never produces an illegal position. `tests/positions.tsv` takes an optional
  fourth column of flags, which is what lets a row exercise `--line` rather than
  only a placement.

  Four rows added: the winning sacrifice from this session
  (`7Q/8/8/8/6p1/5pPb/5PpP/2k3K1 w`, `Qxh3`, mate in 18 at depth 28); a legal
  `--line` whose reached FEN is asserted character for character; the backwards
  pawn capture; and an unreadable token, which must report a different reason
  from an illegal one.

* **Not done, deliberately.** A `--line` that *warns* and analyses anyway was
  considered and rejected. The failure this release exists to prevent is an
  answer to the wrong question being delivered with full confidence, and a
  warning above a fluent analysis is how that happens; the whole value is in
  producing nothing.

Version strings checked across `solve.py`, `SKILL.md` and this file.

---

## 2.16.0 — 2026-08-25

**Legality was a filter on the search. It should be a property of the answer.**

`img2fen.recognize` walked a ladder of crops and stopped at the first reading
`python-chess` called valid. On a position that is not legal chess — a composed
problem, a generated diagram — the correct reading was therefore discarded, the
walk carried on, and a later crop supplied a placement that was legal *because
the network had misread it*. In every one of the three cases examined the shape
was identical:

```
truth    8/8/B1RP4/2K5/NQk5/Q7/q7/8
   0%  conf 1.00  illegal   8/8/B1RP4/2K5/NQk5/Q7/q7/8   <- correct
   2%  conf 0.92  VALID     8/8/k2P4/2K5/Pqn5/q7/q7/8    <- what was returned
```

The white bishop on a6 came back as a black king and the knight on a4 as a pawn,
which is exactly what made the position legal. Nothing downstream could catch
it: one king a side, plausible material, a clean `status()`. The only thing that
separated the right answer from the wrong one was the softmax, 1.00 against
0.92 — and the old rule ignored it.

The rule is now: the highest-confidence reading wins, whatever its legality, and
the legality is reported next to it. Measured on 120 rendered boards, 60 of them
legal placements and 60 not (`scripts/legality_rank.py`, seed 11):

| | correct | wrong | refused |
|---|---|---|---|
| first legal wins (2.15.1) | 42 | **4** | 74 |
| best confidence (2.16.0) | **120** | 0 | 0 |

Split by half: on the legal placements the old rule scored 42 correct and 18
refused, on the illegal ones 0 correct, 4 wrong and 56 refused. The 18 refusals
among *legal* placements were not misreadings either — those positions are legal
only with Black to move, and the walk assumed White. Ranking by confidence takes
the side to move out of the selection entirely.

Every one of the 120 correct readings scored 1.00, which is why the gate at 0.85
never bit here and why these boards say nothing about where the gate belongs.

**Not every illegality is the same illegality.** `solve.py` exited on any
`status() != STATUS_VALID`, which lumped together positions the engine cannot
answer and positions it answers perfectly well. Measured against Stockfish over
UCI:

| position | status | engine |
|---|---|---|
| both kings attacked | `OPPOSITE_CHECK` | no `bestmove` at all |
| no black king | `NO_BLACK_KING` | no `bestmove` at all |
| three white kings | `TOO_MANY_KINGS` | answers — but not about chess |
| nine white pawns | `TOO_MANY_WHITE_PAWNS` | `b3b4`, +5.88 |
| pawn on the first rank | `PAWNS_ON_BACKRANK` | `e1f2` |

The first group now stops the run with the reason in words; the second prints
one line saying the position is unreachable from the start and analyses it
normally. The old blanket refusal threw away real answers on the lower rows, and
on the upper rows it said `<Status.OPPOSITE_CHECK: 1024>`, which names the flag
rather than the fault.

**Cost.** Ranking means the whole ladder is walked instead of stopping early:
2.7 s an image against 1.8 s on the 120-board set, and 0.2 s once the stop at
1.000 is in (these boards reach it on the first crop). Nothing can beat a softmax of
1.000, so the walk still stops there, which recovers most of the difference on
clean diagrams; a diagram that never reaches 1.000 pays the full ladder, and
that is the case where the extra crops are earning their keep anyway.

**Tried and rejected.** Keeping the legality filter and merely *reporting* the
discarded illegal reading as a footnote. It fixes the silent substitution but
leaves the wrong placement as the headline answer, which is the part that
reaches the user; and it still returns 4 wrong boards out of 60 on the illegal half of
the set above, because those runs stop at a valid reading before the footnote is ever
composed.

**The suite can now see this.** `selftest.py` judged a row by its answer line,
so a position with no answer line was simply "no answer" — a refusal that
stopped naming its reason, or an unreachable position that started being
refused instead of analysed, would both have passed green. Two expectation
forms were added, `refuses=` and `says=`, and three rows with them: both kings
attacked, a missing king, and the nine-pawn position that must reach a verdict.
`judge()` itself is checked against seven cases before the suite runs, because
an expectation form that matches everything looks exactly like a passing row.
The suite is 13 rows, 32 s.

**Not changed: the confidence gate at 0.85.** Three images from the Kaggle set
`koryakinp/chess-positions` suggest it is too strict for piece styles outside
the network's training set — a correct reading came back at 0.75 and was
refused, a garbage one at 0.45. Three images decide nothing, and the rendered
boards used above all score 1.00, so they cannot speak to it either. The sweep
needs the real images; `reader_eval.py --dataset koryakin --confidence` is
written and waiting on network access to `kaggle.com`.

---

## 2.15.1 — 2026-08-25

**`SKILL.md` declared the version twice, and only one copy was ever checked.**

The convention says three places must agree: `VERSION` in `scripts/solve.py`,
the `version:` field in `SKILL.md`'s frontmatter, and the top entry of this
file. `selftest.py` has enforced that since 2.3.0 and refuses to run on a
mismatch. It kept passing while `SKILL.md` said, in its own body, **Version
2.13.0** — because there were never three sites. There were four, and the fourth
was not on the list.

The check read the frontmatter with `^version:\s*(\S+)$`. A line of prose
reading `**Version 2.13.0.**` does not match it and was never looked at. The
stale copy survived 2.14.0, 2.14.1 and 2.15.0, and went out in every archive
packaged from them. Nothing downstream depends on that line, so the damage is
confined to a reader being told the wrong build — but that is precisely the
failure the whole convention exists to prevent, and it was sitting in the
paragraph that explains why the convention exists.

Two things went wrong and both are worth separating.

*The number was duplicated.* Two copies of a fact in one file will diverge; that
is not a prediction, it is what happened. So the prose no longer restates it and
points at the frontmatter instead. One file, one declaration.

*The check verified the wrong direction.* Comparing three known sites against
each other cannot find a fourth site nobody registered. A sweep of the whole
skill for version-shaped tokens does not find it either, if it only asks whether
each token names a release that exists — `2.13.0` does exist, so that test
passes. The question that catches it is the opposite one: does anything here
*claim to be the current version*, and is it?

Changed:

* `SKILL.md` no longer names the version in its body.
* `stray_versions()` in `selftest.py` scans `SKILL.md` (below the frontmatter),
  `README.md` and `FAQ.md` for the pattern `version <x.y.z>` and refuses to run
  when one of them is not the current release, exit code 2, before any position
  is analysed.

Verified both ways, which matters for a check whose job is to fire: with the
stale line put back the suite stops with `SKILL.md:7 says 2.13.0` and exit 2;
with the same line corrected to the current release it runs green, so a
redundant-but-right copy is tolerated rather than forbidden. Historical
references — "since 2.10.0", "removed in 2.7.0" — do not match the pattern and
are left alone, since that is how these files normally talk about the past.

Not fixed here: `README.md` and `FAQ.md` are scanned but have no version
declaration to go stale, so the scan is a guard against a future one rather than
a fix for anything present.

---

## 2.15.0 — 2026-08-25

**When the margin ladder finds nothing, `img2fen.py` now locates the board grid
in the image instead of giving up.**

Every crop in `MARGINS` trims the same fraction off all four sides. That is the
right move for a diagram saved with an even border, and the wrong one for a
screenshot taken by hand, where the frame sits a few pixels inside the board on
one side and outside it on another. No symmetric trim lines up with that, so the
8x8 split lands across the seams, every square is read as a smear of two, and
the ladder walks all ten rungs finding nothing — or worse, finds a legal
position built from the wrong pieces.

The grid does not have to be guessed. Square boundaries are the only lines in a
diagram where the colour changes along the whole width, so summing the
horizontal gradient down each column gives seven strong peaks with the files
between them. Fitting an evenly spaced comb of nine boundaries to those peaks
locates the board whatever the crop did, and each cell is then cut on its own
detected bounds. A cell that the crop truncated is padded back to full width
rather than stretched: the missing strip is square background, not part of the
glyph, and stretching it distorts the piece into something the network has never
seen.

This runs as a second pass, only after the ordinary ladder has failed on every
rung, so a well-cropped diagram costs nothing at all. Measured on ten positions
rendered at 512 px and then cropped 5, 3, 2 and 6 pixels in from the four sides:

| | correct | **wrong** | nothing found |
|---|---|---|---|
| margin ladder alone | 0 | **2** | 8 |
| with the grid pass | **10** | **0** | 0 |

The last wrong answer is caught by the confidence threshold from 2.14.0 rather
than by the grid: reading a truncated square still leaves one square unsure, and
that is what the threshold is for. Measured on its own the grid pass gives 9
correct and 1 wrong; the two together give 10 and 0. Over the whole 110-diagram
suite the pass lifts 96 correct readings to 108, with no wrong answers either
way, and the two that remain refused are a diagram scaled down to 320 px where
the ladder finds nothing to begin with.

The cost is nothing on a clean diagram and small on a broken one: median time
per diagram is unchanged at 0.11 s, since the second pass only starts after the
first has failed all ten rungs, and the worst case rose from 1.27 s to 2.38 s.

Changed:

* `board_grid` and `regrid` in `img2fen.py` — gradient profile, comb fit, seam
  snapping, edge padding. numpy and Pillow only; no new dependency.
* `recognize` walks the ladder twice, the second time over the regridded image,
  and yields which pass produced each attempt so `--all` shows it.
* `--no-grid` skips the second pass, for timing comparisons and for the case
  where the fallback itself is suspected.

Tried and rejected: replacing the margin ladder with grid detection outright.
It is slower, and it is worse on the case the ladder was built for — a diagram
with coordinate labels in a margin puts strong gradients outside the board and
the comb fits those instead, which cost a position that the plain ladder reads
without trouble. The two mechanisms fail on different inputs; running the cheap
one first and the general one second keeps both.

---

## 2.14.1 — 2026-08-25

**The confidence threshold added in 2.14.0 was described as more than it is.**

2.14.0 claimed the softmax separates correct from incorrect readings cleanly.
It does on the suite it was measured on, which used three piece sets. Repeating
the measurement across twenty piece sets from the lichess repository, ten
positions each, shows the claim does not hold:

| | reads correctly | **returns a wrong FEN** | refuses |
|---|---|---|---|
| the network, gate at 0.85 | 71 | **19** | 110 |

Six sets are read reliably — cburnett, merida, alpha, cardinal, companion,
tatiana. Eight are refused outright. The remainder are where the damage is: on
`kosal` the network returns wrong positions at a softmax of **1.000**, and on
`leipzig` it is wrong on eight diagrams out of ten. Raising the bar does not
help, because the confidence is not wrong by a little:

| gate | correct | wrong |
|---|---|---|
| 0.85 | 71 | 19 |
| 0.95 | 67 | 16 |
| 0.99 | 66 | 8 |
| 0.999 | 56 | 7 |

By 0.999 there are still seven wrong answers and sixteen correct readings have
been thrown away to get there. A softmax is a statement about the classes the
network was trained on; a piece set outside that training is not a class it can
express doubt about.

The earlier measurement was not wrong, it was unrepresentative: the two
non-default sets in it, merida and alpha, happen to be two of the six the
network knows. Picking the sets it can read and concluding it reads sets is the
sampling error to avoid repeating — the 110-diagram suite is kept, but a claim
about piece sets now has to be made against the twenty-set one.

Changed, documentation only — no behaviour is touched:

* The 2.14.0 entry above is marked where it overstates, rather than quietly
  reworded; what the entry does establish is stated narrowly.
* The message shown when a reading is withheld no longer offers "the piece set
  is one the network was not trained on" as a likely cause. It is a cause of
  wrong answers, but not of the refusals — an unfamiliar set is exactly the case
  the threshold does not catch, and naming it there sends the reader after the
  wrong remedy.
* `SKILL.md` states what the threshold covers, that it is not a defence against
  an unfamiliar piece set, and that the material count remains the check that is.

The threshold stays. It costs nothing, and on the failures it does cover —
images scaled too small, crops that miss the board edge — it turned three silent
wrong answers into refusals without losing a correct reading. It is a filter on
one known failure mode, not a guarantee.

---

## 2.14.0 — 2026-08-25

**`img2fen.py` no longer returns a reading it cannot stand behind.**

The recognizer had no way of saying "I do not know". `read_board` fed
`fen_decode` the argmax of the softmax, so all 64 squares always got a piece,
and the only filter downstream was `chess.Board(...).status()`. A legality check
does not catch a wrong piece: swap a rook for a bishop and the position is still
legal. The failure was therefore silent — a wrong FEN, no warning, and the
verdict that followed answered a position that was never on the board. That is
the same class of defect as the old `--svg [PATH]` optional-value argument, and
it gets the same treatment: make the wrong answer impossible to return rather
than easier to notice.

The softmax turned out to separate the two cases cleanly on the sample measured here. **That claim was too broad and is corrected in 2.14.1 below** — on a wider suite of piece sets the network returns wrong readings at a softmax of 1.000, and no threshold catches them. What the measurement below does support is narrower: the threshold catches the failures that this suite contained, which were a diagram scaled too small and a crop that missed the board edge. Measured over 110
rendered diagrams — ten positions from `tests/positions.tsv` in eleven variants:
sizes 320, 512 and 800, three colour schemes, coordinate labels in a margin,
JPEG at quality 40, the board drawn from Black's side, the cburnett, merida and
alpha piece sets, and a crop that misses the board edge by 2 to 6 pixels on each
side:

| | least certain square |
|---|---|
| reads that were correct (n=96) | min 0.891, median 1.000 |
| reads that were wrong (n=3) | 0.421, 0.653, 0.787 |

`MIN_CONFIDENCE = 0.85` sits in that gap — in this suite. See 2.14.1 for where it does not. A crop whose weakest square falls
below it is not accepted as the answer; the ladder carries on to the next crop,
which often reads the board cleanly. Scored on the same 110 diagrams:

| | correct | **wrong** | withheld |
|---|---|---|---|
| before (`--confidence 0`) | 96 | **3** | 11 |
| after (default 0.85) | 96 | **0** | 14 |

The three wrong answers became refusals and not one correct reading was lost, so
the threshold costs nothing on this suite. Timing is unchanged: the softmax is
already computed, and `probs.max(axis=1).min()` is free next to the 2.05 s the
TensorFlow import costs.

Where the three failures came from is worth recording, because it is not where
it was expected. The network handles unfamiliar piece sets well — merida and
alpha scored 20/20. It failed on a diagram scaled down to 320 px (1 wrong, 3 no
reading) and on the off-by-a-few-pixels crop (2 wrong, 8 no reading). The crop
ladder in `MARGINS` only ever trims symmetrically, so a screenshot taken a
little inside the board on one side shifts the whole 8×8 split and every square
lands across a seam.

Changed:

* `read_board` returns `(placement, confidence)` instead of a bare string;
  the confidence is the softmax of the *least* certain square, since one bad
  square is enough to spoil the placement.
* `recognize` takes `min_confidence` and yields a fourth item, the confidence.
  A legal-but-untrusted crop is reported as `not trusted: ...` and the walk
  continues.
* Every crop line now prints its confidence, so `--all` shows why a diagram was
  refused instead of leaving it to be guessed.
* When the ladder ends with a reading that was gated out, the closing message
  says so and names the likely causes, rather than claiming no legal placement
  was found — those are different problems and want different remedies.
* `--confidence P` sets the bar; `--confidence 0` restores exactly the old
  behaviour for anyone who intends to check the result by hand.

Tried and rejected: raising the bar to 0.90, which is above the 0.891 seen on a
correct read and would have started refusing good diagrams for nothing.

Not done here, though the measurements pointed at them. Locating the grid from
the image's gradient profile instead of trimming symmetric margins fixed the
off-by-a-few-pixels crop for this same network — 9 correct and 1 wrong, against
0 correct and 2 wrong with the `MARGINS` ladder. A second recognizer built on
template matching against rendered glyphs needs no TensorFlow at all, reads a
diagram in 0.031 s against 0.107 s plus a 2.05 s import, and refused all 20
foreign-piece-set diagrams rather than guessing — but it cannot read them, where
the network can. Both are worth doing and both are larger than this entry.

---

## 2.13.0 — 2026-08-24

**The "the number understates the position" warning now fires on the
full-enumeration path too, and both copies of the rule became one.**

The warning existed on the sampled-defences path only. On the full path its
condition began with `holds and` — the list of replies that survive — so it
could not fire when every reply loses. That is exactly the case it was needed
for on `8/8/8/4b1p1/5pP1/R3k2P/3p4/5K2 b`, the mate in 13 measured in 2.12.1:
at the defaults, `--scan full` printed eleven mated replies, a headline of
`+8.00`, and `Verdict: the win is forced, every reply loses (12)` — with no
hint that the twelfth reply, `Rxc3+`, was both the toughest and the only one
not resolved to a mate. Everything printed was true and the reader still came
away with "won by eight pawns" instead of "mate in 13". The same position on
the sampled path, four defences instead of twelve, did print the warning: the
narrower output carried the better verdict.

**The new line says less than the old one, deliberately.** Where every reply
loses, the win itself is proved and only the distance is open, so
`v_forced_mates` claims exactly that and points at the setting that resolves
it. `v_branch_mates` keeps its stronger wording, because on that path the
forcedness genuinely is unresolved. Conflating the two would have made the
existing message wrong in the new case.

**The rule now lives in `headline_understates()`, called from both paths.**
The drift is the point: two independently written copies of one rule, one
using "mated replies outnumber the ones that hold" and the other "mated
replies outnumber the ones that are not mated", agreeing on most positions and
disagreeing on this one. Each was defensible where it stood; nothing made the
disagreement visible, and the class of bug is unbounded as long as the
duplication remains. `winning_mates()` alongside it also fixes a latent
inconsistency — the full path tested `is_mate() and mate() > 0`, which is
`False` for `chess.engine.MateGiven`, the score `enumerate_replies` assigns to
a reply that is mate on the board. A reply that is *already* checkmate was
therefore not counted among the mated ones.

Tests: `tests/test_verdict.py` asserts both messages on constructed reply
tables, including the eleven-of-twelve case and the all-mated case where the
distance *is* established and nothing extra should print. It exercises the
predicate directly rather than through a search, so it costs no engine time
and cannot be turned green by a lucky depth.

**Not changed.** The `--probe-step` versus `--mate-probe` question from 2.12.1
stays open, and line 265 of `SKILL.md` stands as written. This entry is about
reporting what the search already found, not about finding more.

---

## 2.12.1 — 2026-08-24

**The ladder measured seven ways on one position, and the wrapper's output
declared off-limits to pipes.**

No behaviour changed. Both entries are things a session got wrong in practice.

**Seven configurations on `8/8/8/4b1p1/5pP1/R3k2P/3p4/5K2 b`, a mate in 13.**
All rows below `--min-depth 26 --time 20 --scan off` except the defaults row,
one core, Stockfish 16:

| ladder | re-probe | result | total |
|---|---|---|---|
| `--mate-probe 0` | — | +35.90, no mate | 3.7 s |
| 5 × 0.3 (defaults throughout) | on | +8.10, no mate | 2.5 s |
| 5 × 0.3 | on | +36.10, no mate | 4.7 s |
| 12 × 0.3 | off | +36.48, no mate | 6.1 s |
| 8 × 1.0 | off | +36.47, no mate | 9.3 s |
| 12 × 1.0 | off | mate in 13 | 12.9 s |
| 5 × 3.0 | off | mate in 32 | 16.0 s |
| 5 × 3.0 | on | mate in 13 | 21.7 s |
| 12 × 3.0 | on | mate in 13 | 40.6 s |

Three things are worth keeping. First, depth is not the variable: with the
ladder off the search reaches the same depth 25 in 3.7 s and reports +35.90,
and raising `--min-depth` to 26 changes nothing. This is the hash-warming
effect already recorded above, on a second position.

Second, the outcome is not monotone in either parameter. 12 × 0.3 and 8 × 1.0
miss; 5 × 3.0 hits. That is consistent with the warming being incidental — the
rungs are not finding the mate, they are leaving forced lines in the shared
table — and it is a warning against reading either number as a dial. Note in
particular that 8 × 1.0 misses where 12 × 1.0 hits: the ceiling is not inert,
so "raise the step, not the ceiling" would be the wrong lesson to draw from
this position alone.

Third, the `5 × 3.0` pair brackets what `--reprobe-step 0` costs: mate in 32
without the re-ask, mate in 13 with it, for 5.7 s. The descent took two rungs,
not nineteen — `go mate 32` returns the distance the engine actually finds
rather than the one it was asked about, so a badly inflated distance collapses
in one rung. The mate in 32 was never wrong about the position mating; it was
wrong about the number, which is the part a reader would act on.

**Left open.** Line 265 of `SKILL.md` says that when the reply list is mated
and the headline is not, the distance is unresolved and settings will not fix
it — with `--mate-probe 12` named as tried and rejected on
`8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w`. On the position above, settings did fix
it. One counterexample does not overturn a measured "do not", and the two
positions may differ in kind rather than in degree; the honest state is that
the rule holds on its own position and fails on this one. Resolving it needs
the pinned sample re-run with `--extra "--probe-step 3"` against the current
default, roughly eight minutes a configuration. Until then line 265 stands as
written.

**`stage.py`'s output must not be piped into a parser.** The wrapper is
transparent: stdout and stderr pass through unchanged, the exit code is
propagated, and the script contains no JSON — `grep -c json scripts/stage.py`
is 0. A session piped a wrapped `solve.py` into `json.load`, which destroyed a
completed 2.8 s analysis and forced a second search; `cat` on the redirected
file then returned inside the surrounding tool harness's own JSON envelope,
which looked exactly like proof that `stage.py` emits JSON, and the wrong
diagnosis survived into a written answer before being caught. The rule is now
in Step 3 next to "do not run a command outside the wrapper", with the reason,
because the failure is self-confirming and re-derivable by anyone who tries the
same thing.

---

## 2.12.0 — 2026-08-21

**`scripts/compare.py`: the source diagram and the position as read, on one
sheet with aligned grids.**

Step 4 has always asked for the rendered board to be compared against the
original. Until now that meant two loose images — different sizes, different
piece styles, one of them with its own coordinate frame — and comparing them
meant counting files by eye on each board separately, per piece. That is exactly
the work the check exists to remove, and a check that is tiring to perform is a
check that gets skimmed.

The sheet crops the source board to its outer edge, scales both boards to 768 px,
and rules the same 8×8 grid over each, so a square is at the same point in both
halves and a misplaced piece shows up as a horizontal offset rather than as a
discrepancy between two counts.

**Finding the board is the whole difficulty, and the first attempt was wrong.**
The two square colours are the most common pixels on a 2D diagram, so the
bounding box of everything matching them should be the board. Matching against
the corner of the quantised colour bin with a tolerance of 40 also matched
anti-aliased grey label text around (200,200,200) — a light tan's channels are
not far enough apart for grey to be excluded by distance alone — and the box grew
to swallow the coordinate margin. On the test image it returned (21, 20, 938,
946) where the board is (54, 20, 938, 905), and the resulting sheet was
misaligned by about half a square: worse than no sheet, because it looks correct.
Three changes fixed it: match against the centroid of each colour cluster rather
than its bin corner, require a minimum saturation so that greys are excluded by
kind rather than by distance, and accept a row or column only when most of it is
board, so scattered matching pixels cannot stretch the box.

**It refuses rather than guessing.** A candidate that is not roughly square, or
that covers less than a quarter of the image, is rejected; the source is then
shown whole with a note printed on the sheet saying the grids may not line up.
Photographs of physical boards and diagrams whose page background matches their
light squares both land here. `--no-crop` forces it, `--flipped` handles a
diagram drawn from Black's side.

**What it does not check.** A board read from the wrong side produces a
comparison in which both halves agree, because every piece is in a plausible
place — the reading is 180° out, not misplaced. The sheet cannot see that, step 2
and the coordinate labels can, and SKILL.md now says so where the sheet is
introduced, so the new tool does not quietly displace the check that catches the
worse error.

Dependencies are Pillow and NumPy, usually already present; `compare.py` exits
with the install line when they are not. This is not the recognition stack and
does not pull in TensorFlow: the reading is still done by eye.

Tests: `tests/test_compare.py` builds synthetic diagrams with the board at a
known offset and asserts the detector lands within a few pixels of it — including
the grey-label case above, an already-tight crop, and a non-square candidate that
must be refused. A detector has no ground truth of its own, so the fixtures carry
the answer.

---

## 2.11.0 — 2026-08-21

**The timing journal now has an end.** `stage.py --stop` marks the work as
finished; `--report` measures from `--start` to that mark instead of to the
moment the table is printed.

The old behaviour was wrong in exactly the case the journal is for. Printing
happens only when the user asks, and the asking comes after the answer has been
read — so the span included the user's own reading and typing time, filed under
`other: gaps not covered by a measurement`. The session that prompted this: four
seconds of engine work, fifteen seconds of measured work in total, one pause
while the user read the verdict, and a table reading **549 s total, 534.6 s
(97%) in `other`**, with the mate ladder, both searches and all three installs
rounded to 0%. The number that meant nothing was the whole table, and the numbers
that answered the question were invisible. This is not a rounding complaint: the
report is read as "where did the time go", and it answered with a duration
nobody spent working.

Three details, each chosen against a plausible alternative:

* **A measured row after a stop cancels it.** The alternative — a stop that
  sticks until explicitly cleared — makes a follow-up question silently
  unmeasured, which is the same class of bug in the other direction. Cancelling
  means the journal reopens by itself and only needs stopping again.
* **A journal that was never stopped still reports, with a different coverage
  line** saying the total includes idle time. Refusing to print would punish the
  user for the assistant's omission; printing the old silent number would
  preserve the bug.
* **`--stop` closes any bracket left open by `--begin`,** labelled
  `closed by --stop`. A bracket open at the end of the work is a step that would
  otherwise vanish from the table entirely.

`--stop --at-last` backdates the mark to the close time of the last measured
row, which is already recorded in the journal's fifth field. It exists so a
session where the stop was forgotten can still be recovered rather than thrown
away; it is a repair and is documented as one.

**`selftest.py` no longer writes into the live journal.** Found while testing
the above, not looked for: the suite runs `solve.py` outside the wrapper, and
`solve.py` journals its stages either way, so ten suite positions landed in the
session's own journal as a single unlabelled `not wrapped by stage.py` row with
sixty stage rows nested under it. The suite now points `CHESS_TIMELINE` at its
own file. Anything else that runs `solve.py` outside the wrapper needs the same
treatment.

Tests: `tests/test_stage.py` covers the stop, the cancellation, the auto-closed
bracket, the fallback coverage line and `--at-last`. `solve.py` is untouched
apart from `VERSION`; the version moves because `selftest.py` refuses to run when
`SKILL.md`, `solve.py` and this file disagree, and a green suite against a build
nobody can name is worth very little.

---

## 2.10.0 — 2026-08-21

Four changes, all from one exercise: the skill was audited for positions where
the *engine* is wrong rather than the reading. Three classes turned up, and each
of the changes below is one of them made visible in the output.

**`--quick` no longer switches off the mate ladder; `--fast` does.** The flag was
documented as "evaluation only, no defence analysis" and in fact also skipped the
ladder and the re-probe, which made it mate-blind. That matters because `--quick`
is exactly what SKILL.md recommends for *was this move a mistake* — two runs,
before and after, both blind to a mate on either side of the move. Measured on a
16-position `matetrack` sample (`--sample 20260820 --budget 15`): **10 to 12
mates found by default, 2 with the ladder off**, about 80 s against 10 s. The
range is the machine, not the change: the ladder's rungs are timed, so the same
command on the same build gave 12 in the morning and 10 in the afternoon. 2.10.0
scored 11 on the run that followed the 10. Re-measure both sides before reading
anything into a difference of one or two. The speed was real
and is still available under `--fast`, which now prints a line saying the ladder
is off. `--mate-probe` combined with `--fast` is an error rather than being
silently ignored — that silence is how an explicit `--mate-probe 11` ran no
ladder at all during the audit, with nothing in the output to show for it.

**The halfmove clock is printed, and probed.** The fifth FEN field decides games
and legality never questions it: `8/8/8/8/8/2k5/8/KBN5 w` reads `+2.57` with `0`
there and `0.00` with `90`. Diagrams carry no clock and `img2fen.py` writes `0`
unconditionally, so the number in that field is as often an assumption as a
reading. It now appears on the position line, with a note saying which it might
be. On top of that, `--fifty-probe` re-evaluates the same placement with the
clock at 90 and prints what happens — automatic at seven men or fewer and on a
decisive evaluation for either side, about two seconds.

**The probe is one-sided and the note says so.** Measured at `hm = 0 | 50 | 90`:

| position | truth | | | |
|---|---|---|---|---|
| `8/p7/kpP5/qrp1b3/rpP2b2/pP2b3/P7/K7 w` | draw, fortress | −11.25 | −7.98 | 0.00 |
| `8/8/8/8/8/2k5/8/KBN5 w` | mate in ≤33 | +2.64 | +1.80 | 0.00 |
| `1K1k4/1P6/8/8/8/8/r7/2R5 w` | won, Lucena | +8.08 | +7.02 | 0.00 |
| `r5k1/pp3ppp/8/8/8/5N2/PP3PPP/3R2K1 w` | won, a rook up | +5.43 | +5.27 | +5.36 |

The Lucena row is why the note stops short of calling a collapse a draw: a
textbook won rook ending fails the probe exactly as the fortress does, because
building the bridge takes more than ten plies. What separates them is
`--playout N`, new here: the engine plays the position out against itself and
reports the ply at which the clock first resets. Lucena resets at ply 9 and
finishes 1-0; the fortress ran 98 plies with no capture and no pawn move even
with the strong side given ten times the thinking time. A playout cut short by
the budget says so — truncated, it proves nothing.

**A verdict that contradicted the output above it is gone.** On
`8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w` the run printed `+2.67`, then three
replies already mated, then `Verdict: the win is not forced`. The position is a
forced mate in 10. A mated reply proves the position mates at least down that
branch; the old verdict line was derived from the unresolved main line and
stated the opposite. It is now replaced, in that case, by a line saying the
number understates the position and that whether the win is forced is not
established either way.

The trigger is narrower than the first attempt, which replaced the verdict
whenever any reply was mated. That broke the position in README.md, where `Rf7`
is mated, `Kh8` holds, and *the win is not forced* is precisely the right
answer. It now needs two or more mated replies outnumbering the ones that hold:
a single mated loser is ordinary, most of the list being mated while the
headline is a centipawn score is not.

**Tried and did not pay, recorded so it is not re-derived.** On that same
position no setting reaches the mate: `--min-depth 24 --time 20` gives `+2.73`,
`--mate-probe 12 --probe-step 2` gives `+5.70`, and `go mate 8`, `10` and `12`
at twenty seconds each all return a centipawn score. MultiPV 3 reports `#+10` at
both 5 s and 15 s while MultiPV 1, 2 and 4 do not — search luck, not a setting,
and it was not turned into one. The tell is the disagreement inside the output,
which is what shipped instead.

**Caught during the work, and worth writing down.** The defence section pushes
the best move onto the board and never pops it, so from that point on `board` is
the position *after* the best move. The fifty-move probe was written against it
and printed an evaluation with the sign reversed -- a plausible-looking number
for a position nobody asked about, which is the exact failure mode this skill
exists to prevent. Both new checks now work from an explicit snapshot taken
before the push, and there is a comment at the snapshot saying why it is there.

**Also**: at seven men or fewer the position line now carries a
`tablebase.lichess.ovh` query URL. No Syzygy files are installed and the egress
proxy refuses that host, so the link is for the user to open; without it, K+B+N
against a bare king goes out as "about two and a half pawns" and stays wrong at
any depth. `tests/hard.epd` collects the eight positions behind this entry with
the expected shape of each answer; none of them is assertable, so it is a
by-hand list rather than a suite.

---

## 2.9.0 — 2026-08-20

The diagram is a PNG when the machine can make one. `--diagram
{auto,png,svg,none}` replaces the on/off pair from 2.8.0.

**Why, and it is not that PNG looks better.** 2.8.0 traded away half of the
reading check without noticing: the assistant reading `solve.py`'s output can
open a PNG and cannot open an SVG, so the position stopped being verified by
machine and was left to the material counts and the user's eye. A PNG restores
the like-for-like comparison against the source diagram — which is the whole
argument for rendering a board in the first place.

**Measured on this container**, since both routes needed checking before one
could be recommended:

| route | install | render |
|---|---|---|
| `apt install librsvg2-bin` | 3.2 s | 0.05 s |
| `pip install cairosvg` | 2.6 s | 0.38 s |
| ImageMagick (`convert`) | already present | **fails** |

ImageMagick is the trap of the three. `convert` is installed on this image and
does not rasterise SVG itself: it delegates to `rsvg-convert` and dies with a
delegate error when that is missing. Detecting it as a rasteriser would have
produced an empty file and a confident message about having written a diagram.
It is excluded by name, with the reason in `find_rasteriser()`.

**Changes:**

- `find_rasteriser()` prefers `rsvg-convert`, falls back to importing
  `cairosvg`, returns `None` otherwise. cairosvg is imported rather than
  located, because it loads libcairo at import time and raises `OSError`, not
  `ImportError`, when the C library is missing — hence the broad except.
- `save_svg()` becomes `save_diagram(..., fmt, tool)`; PNGs render at 780 px
  wide, since 390 rasterises legibly and blurs the moment it is zoomed.
- `--diagram auto` (the default) writes PNG where possible and SVG otherwise.
  An explicit `--diagram-path` ending in `.svg` selects SVG, because writing a
  PNG into a file called `board.svg` is worse than either format. `--diagram
  png` with no rasteriser prints a note and writes SVG rather than failing.
- `--no-svg` and `--svg-path` survive as aliases for `--diagram none` and
  `--diagram-path`; `--svg` stays an accepted no-op.
- A `rendering the diagram (png via rsvg-convert)` stage appears in the timing
  journal, so the cost is visible rather than folded into the legality check.
- Setup in `SKILL.md` and `README.md` gains the optional third install, with
  the measurements above and the reason it is worth three seconds.

**A bug found by testing, not by reading:** the format variable was first
called `fmt`, which shadowed the scoring helper of the same name defined later
in `run()`, and every evaluation died with `TypeError: 'str' object is not
callable`. It is `diagram_fmt` now, with a comment saying why. The failure was
invisible under `--quick` in the first smoke test and appeared only on a full
run — a reminder that the smoke test has to reach the verdict, not just the
board.

`selftest.py` passes 10/10. `epdcheck.py` is untouched; neither reads the board
output.

---

## 2.8.0 — 2026-08-20

The position-as-read is a rendered diagram now, not a text grid. `save_svg()`
runs on every invocation instead of only under `--svg`, and the letter grid
becomes the fallback.

**Why.** 2.6.0 and 2.7.0 were both about fonts — a boxed glyph grid that skewed
outside a monospace terminal, then plain letters that survive any font. A
rendering ends that line of argument rather than continuing it: it depends on no
font at all. It also makes the comparison the check exists for a like-for-like
one. The reading errors this catches are positional — a file shifted by a
miscounted run of empty squares, a piece read in the wrong colour — and against
a source diagram they are visible at a glance on a board, where in a grid of
letters each one has to be traced square by square.

**Cost, stated plainly.** The assistant cannot open the SVG, so the automatic
half of the check now leans on two things that were already there: the per-side
material counts, and the eight rows of piece letters `chess.svg` writes into the
file's own `<desc>` element. `--text-board` prints the grid alongside the
diagram when a reading is in doubt.

**Changes:**

- `save_svg()` is unconditional; `coordinates=True` is passed explicitly, since
  a piece that cannot be named without counting squares loses the property the
  labelled text grid was built around.
- `default_svg_path()` replaces the old `board.svg`-in-cwd default: first
  writable of `/mnt/user-data/outputs`, the working directory, a temporary
  directory. The old default was acceptable for a flag nobody passed and wrong
  for something that runs every time — the working directory is usually the
  skill's own folder, and a read-only install would have failed on every run.
- `--no-svg` prints the letter grid instead. This is the flag for a plain-text
  surface, where a path to a file nobody can open is worth less than a grid.
- `--text-board` prints the grid as well as the diagram.
- A failed write warns and falls back to the grid, as before. No run ends up
  with no reading check at all.
- `--svg` stays as an accepted no-op. This is not the mistake the `--board-style`
  note in `solve.py` warns against: that flag would have gone on being accepted
  while doing nothing it promised, whereas this one still delivers exactly what
  it says. The help text says the rendering is now unconditional.
- `SKILL.md`, `README.md`: the board section, the flag list, the report
  checklist and the sample output follow the new default. The instruction to
  show the board in the answer is now an instruction to show the diagram — a
  file rendered and never displayed checks nothing.

`selftest.py` and `epdcheck.py` are untouched: neither reads the board output.

---

## 2.7.0 — 2026-08-20

Reverts the boxed Unicode board introduced one version earlier. The
position-as-read is printed as plain letters again, and `--svg` is now the
supported way to get a diagram that actually looks like a diagram.

### The boxed grid is gone

`unicode_board()`, `_UNICODE_PIECES` and `--board-style` are removed;
`ascii_board()` is the only text rendering and is no longer selectable.

2.6.0 justified the boxed grid on the grounds that a piece read in the wrong
colour becomes a shape difference (`♕` vs `♛`) rather than a case difference
(`Q` vs `q`), and that reasoning still holds *in a monospace terminal*. What it
missed is where this output is actually read. Box-drawing characters and chess
glyphs line up only when the font gives both the same advance width. In a chat
client, a notebook or a rendered Markdown pane it usually does not: the glyphs
come from a symbol fallback font at a different width, every row shifts by a
different amount, and the grid arrives visibly crooked with the rank labels no
longer under each other.

That is worse than ugly. The board exists to be compared against the diagram,
and a verification aid that looks broken gets skimmed instead of read — so the
cosmetic failure costs precisely the check the grid was introduced to
strengthen. The colour-confusion argument it was trading against is already
covered by the per-side material counts printed directly underneath, which
catch a colour swap *and* a dropped piece, and which no font can misalign.

`--board-style ascii` was the escape hatch for exactly this, which in hindsight
was the tell: a default that needs a documented workaround for common
environments is not a default. It is removed rather than kept as an accepted
no-op, so a stale `--board-style unicode` fails loudly instead of quietly
meaning nothing.

### `--svg` is now the answer to "I want a real board"

No change to the flag, only to its standing. In 2.6.0 it was a rarely-needed
extra for cluttered positions, with the boxed grid billed as enough for the
normal case. It is now the supported route to a rendered diagram, and `SKILL.md`
says so: draw a real one through `chess.svg` — still a dependency-free path,
since it ships inside `python-chess` — rather than imitating one in text. The
same instruction is given to the assistant about its own answers, since a
hand-drawn box grid in a reply fails for the same font reasons as a printed one.

### Also fixed

`SKILL.md`'s body claimed **2.5.0** while its frontmatter and `VERSION` both
said 2.6.0 — the exact three-way disagreement the file's own opening paragraph
warns about, sitting inside the paragraph that warns about it. All three now
read 2.7.0.

---

## 2.6.0 — 2026-08-20

The board printed for verification was plain letters on a grid. It now defaults
to a boxed Unicode grid, and the position can also be rendered to a real SVG
diagram.

### Unicode board by default

`unicode_board()` draws the same 8x8 placement as before, but with box-drawing
characters for the grid and the standard hollow/solid chess glyphs (`♔♕♖♗♘♙` /
`♚♛♜♝♞♟`) for pieces instead of `K`/`k`-style letters. This is not only
cosmetic: a piece read in the wrong colour was previously only a case
difference (`Q` vs `q`), easy to miss at a glance; it is now a shape difference
as well, which is closer to what actually goes wrong when a diagram is misread.
Costs nothing extra — the glyphs are plain Unicode text, no new dependency.

The one real risk is font-dependent: a terminal or font that renders the chess
glyphs at double width will misalign the grid, where the old letter grid would
not. `--board-style ascii` restores the previous plain-letter output for
exactly that case. No default was found that is safe everywhere, so this is a
switch rather than a guess.

### `--svg` for an actual rendered diagram

`--svg` writes the position as an SVG file via `chess.svg`, which ships inside
`python-chess` — already a hard dependency, so this is free in the sense
`SKILL.md` cares about: nothing to install, nothing that can fail to install on
some platform. `--svg-path PATH` chooses the destination (default `board.svg`)
and implies `--svg`. Off by default; the boxed Unicode grid is enough for the
normal case, and this is for when a diagram is cluttered enough that a real
rendering is worth the extra file.

**The flag was `--svg [PATH]` first, and that spelling was dangerous.** With an
optional value and an optional positional FEN, `solve.py --svg "<fen>"` handed
the FEN to argparse as the *filename* and analysed the **starting position**
instead — no error, no warning, a confident verdict on a position nobody asked
about. That is the exact failure class the rest of this skill is built to
prevent, arriving through the front door. Splitting the path onto its own flag
removes the ambiguity rather than trying to detect it: `--svg` now consumes no
value, so nothing it precedes can be swallowed.

**A failed write no longer aborts the run.** It used to raise straight out of
`run()`, losing a completed search because a convenience file could not be
created. The write is now guarded and downgrades to a warning that says the
analysis is unaffected.

**Rejected: rasterising to PNG.** `chess.svg` produces SVG only; converting to
a raster image needs a converter such as `cairosvg`, which pulls in a native
Cairo dependency not guaranteed to be present or installable everywhere this
skill runs. An SVG opens directly in any browser, so the conversion buys
nothing but a new way to fail on some platforms and not others.

---

## 2.5.0 — 2026-08-20

The mate ladder could report a mate longer than the one that exists. Fixed by
re-asking the shorter distances with real time, but only after a mate is known
to exist.

### Fixed — a timed-out rung looked exactly like a proved absence

On `8/1Np1nN2/r3p1p1/p1Q5/3pkb2/B1R2pnK/3p4/5B2 w` the run reported `Bd3+ mate
in 6` and the journal line `mate ladder: 5 rung(s) of 0.3 s, no mate up to 5`.
The position is a mate in 4: `1. Kg4 Nxf1 2. Qe5+ Bxe5 3. Ng5+ Kd5 4. Rc5#`,
with all 31 replies to `Kg4` losing. Two failures had to line up, and both are
ordinary rather than exotic:

* the first move is a quiet non-checking king move, which iterative deepening
  prunes — the case the ladder exists to cover;
* `go mate 4` here needs more than the 0.3 s the rung is given, so the ladder
  *also* missed it, and its output said `no mate up to 5` in exactly the words
  it uses when the absence is real.

With `--probe-step 6` the same build answers `Kg4 mate in 4` at depth 7 in
8.3 s, which is what identified the cause.

### The fix, and why not the obvious one

Raising `--probe-step` for everyone was rejected. The ladder's cost is paid by
every position and most positions have no mate at all, so five rungs at 6 s is
up to 30 s of nothing — the entire default budget — in the common case. The
asymmetry is the point: *is there a mate at all* has to be cheap, *is there a
shorter one* can afford real time, because by then a mate is in hand and such
positions are rare.

New `Session.probe_shorter`: given a mate in m, ask `go mate m-1` at
`--reprobe-step` (default 3 s), and descend again only if it hits. It runs
after the main search and only when the reported score is a mate for the side
to move. The move the main search preferred is demoted to runner-up rather than
dropped: it still mates, and `the second move mates too` is more use than a
blank line. The stage has its own `--timing` row, so its cost cannot be
mistaken for search time.

### Rejected on measurement — the ascending re-probe

The first attempt reused `probe_mate` and climbed from n = 1 to m-1, capped at
`--mate-probe`. It is the obvious shape and it is wrong: on a suite weighted to
mate in 7–10, every re-probe spends five rungs disproving mates in 1, 2, 3, 4
and 5, none of which was the question. `go mate n` asks *at most n*, so a single
rung at n = m-1 settles the whole thing.

Pinned sample, `--limit 24 --sample 20260820 --budget 15`, one core, measured in
one session so the three rows are comparable:

| build | mates found | at published distance | time |
| --- | --- | --- | --- |
| `--reprobe-step 0` (2.4.0 behaviour) | 14/24 | 8 | 70 s |
| ascending re-probe from n = 1 | 13/24 | 8 | 212 s |
| descending, `go mate m-1` (shipped) | 14/24 | 12 | 107 s |

The ascending row is the whole argument: three times the time, nothing
converted, and one mate lost outright because the wasted rungs exhausted the
15 s budget before the enumeration finished.

On the position that started this, descending costs 3.6 s in one rung and turns
`Bd3+ mate in 6` into `Kg4 mate in 4`.

**The 2.4.0 entry quotes 10 at the published distance on this seed; this machine
gives 8 with the same build behaviour.** That is hardware, not regression. Re-run
the baseline in the same session as the change or the comparison means nothing.

### Not done

* **Making the first ladder adaptive** (start at 0.3 s, grow the step as the
  rungs climb). It shifts the same cost around rather than removing it, and it
  would still have missed this position — the failing rung is n = 4, near the
  top of the ladder, where an increasing step is at its most expensive.
* **Trusting the search's mate distance and skipping the ladder when it
  reports one.** That is what 2.4.0 effectively did, and it is what produced
  the wrong answer: the search's distance is an upper bound, not a proof.

---

## 2.4.0 — 2026-08-20

The timing journal was recordable but not discoverable. Documentation only; no
code changed.

### Fixed — the journal had no way in

`SKILL.md` and `references/timing.md` both said *do not print the table unless
the user asks*, and neither said anything about telling the user it exists. The
answer template's five points — move, defences, evaluation, critical moment,
board and link — had no sixth. `solve.py` ends on a bare `Search time: 3.7 s of
a 30 s budget`, which is read by the assistant rather than the user and mentions
neither `--timing` nor the whole-chain journal.

So the arrangement collapsed in a way neither file noticed: the journal runs on
every analysis, cannot be started retroactively — which is the entire reason it
runs always — and yet nobody who had not read `references/timing.md` could learn
it was there. Recorded on every run, offered on none.

### Changed — offer once, at the end of a slow answer

- **A sixth point in the answer template.** One short closing line offering the
  breakdown, *only when the run was slow enough to notice*: TensorFlow was
  installed, the user was left waiting, or the budget warning fired.
- **The Timing section is now two-sided.** It still forbids printing the table
  unasked; it now also requires the offer when it would mean something. The line
  that matters: the offer costs a line, the table costs the answer.
- **`references/timing.md` names the asymmetry** rather than only describing the
  split, so the rule is not re-derived one-sidedly by the next person to read it.
- The setup section and the reference index mention the offer, so the rule is
  visible without reading to the end.

The threshold is doing as much work here as the rule. An offer attached to every
run is skipped like any other boilerplate, and the feature is then unreachable
again for a different reason — which is why *do not offer it after a two-second
answer* is written down as plainly as the offer itself.

### Verified

`selftest.py`: 10 passed, 0 failed. Five scripts compile, three version
declarations agree, benchmark position unchanged.

---

## 2.3.1 — 2026-08-20

Validation against the published `matetrack` suite, and two parser defects it
found. No change to the search itself.

### Fixed — `epdcheck.py` misread two kinds of row

Both were found by running against the real file rather than by reading the code.

- **The en-passant field was being padded away.** EPD supplies four fields; the
  runner padded to four and appended counters, but built the FEN from a string
  the distance had already been stripped out of, so the fourth field could be
  lost. Six of the 6554 matetrack problems are solved only by an en-passant
  capture, and without that field they are different positions with different
  answers.
- **Negative distances were silently skipped.** Twenty-six rows carry `bm #-N`,
  meaning mate *against* the side to move. The distance pattern accepted no
  minus sign, so those rows parsed as having no distance and were dropped from
  the count. They are now kept and judged, and the **sign is checked before the
  distance**: a mate found for the wrong side is the opposite answer, not a near
  miss.

All 6554 rows now parse and every one produces a legal position.

### Measured — matetrack

Source pinned so the run can be repeated:
`raw.githubusercontent.com/vondele/matetrack/master/matetrack.epd`,
sha256 `8ba5712234ba0cb2a1f1b1934872d1d30ba5e01c80482844dccccd4bc2eefd72`,
6554 problems weighted towards mate in 7 to 10.

Paired on the same 24-position sample (`--limit 24 --sample 20260820 --budget
15`), the only difference being the ladder:

```
             shortest  longer  none   total found   wall clock
with ladder        10       4    10        14/24         62 s
without             2       3    19         5/24         25 s
```

The recipe is in `SKILL.md` so the numbers can be re-run rather than believed.
Do not run the whole file: at fifteen seconds a position it is a day's work.

### Found — the ladder works mostly through the hash table

Worth writing down because it contradicts the obvious model of what the ladder
does, and would otherwise be re-derived wrongly.

The ladder only climbs to five, yet on the sample it rescued problems published
at mate in 13 and mate in 20. The rungs did not find those. On
`k7/Bp6/1P6/6p1/8/8/6K1/7N w` the ladder reports *no mate up to 5* and the run
then returns mate in 13; with `--mate-probe 0` the same run stops at `Nf2 +8.96`
and stays there at ten times the time. Verified independently on a cold engine
with a fresh game key: `go mate 13` confirms the mate in 2 s, and a plain deep
search finds a mate in 15 — longer, but real.

The mechanism is the shared transposition table. `go mate n` searches store
forced lines; the ordinary search afterwards reads mate scores out of the table
instead of having to re-derive them past its own convergence stop. So the ladder
should not be judged by whether a position's mate is within five moves, and
shortening it to save time would cost more than the arithmetic suggests.

### Checked and not a defect

The convergence stop can report a depth one lower than the depth at which it
decided — `depth 17` while the stability streak was counted at 18. This is the
completed-iteration invariant working as intended: the decision is taken on the
first line of an iteration, and what is reported is the last iteration that
arrived *in full*. Reporting the incomplete one is the bug this skill already
had; this is its correct form.

---

## 2.3.0 — 2026-08-20

Closes the three gaps the previous release listed as known: the mate ladder, the
regression suite, and a version that is declared in several places and checked in
none. Nothing in the diagram-reading path changed.

### Added — the mate ladder

`Session.probe_mate()` asks `go mate n` for n = 1 up to `--mate-probe` (default
5), `--probe-step` seconds a rung (default 0.3), before the main search.

This is a correctness fix, not an optimisation. Iterative deepening prunes a
sacrificial mating move as unpromising, so a composed mate in three comes back as
a plain evaluation — the verdict is then wrong in kind, not merely imprecise.
`go mate n` asks a different question, does a mate in at most n exist, and answers
it in milliseconds when one does.

Details that matter:

- **The ladder climbs rather than descends**, so the first rung that answers gives
  the shortest mate it can see. Each rung accepts only a mate no longer than it
  asked for: the engine may return a longer one it happened to notice, and that is
  not what the rung proved.
- **A truncated PV is filled in** by a follow-up search to depth 2n+2 over the
  now-warm hash table. If that fails, the short line is kept rather than dropped.
- **When the ladder hits, the main search is capped at depth 2n+2.** There is
  nothing past that worth having.
- **When the ladder and the search disagree about whether a mate exists, the
  ladder wins** and its line is reported, with a line of output saying so. Without
  this the ladder would find the mate and the printed answer would still not have
  it — which is most of the bug it was written to fix.
- **Skipped under `--quick` and `--nodes`**, where speed and reproducibility
  respectively matter more than finding a composed mate.

Measured, paired on the same five-problem suite, the only difference being
`--mate-probe 0`:

```
             shortest  longer  none
with ladder         5       0     0
without             2       1     2
```

The cost is about **1.7 s** on a position where the ladder finds nothing, which is
most positions in ordinary use. Measured on a quiet opening position: 1.7 s of
ladder, and the main search then ran to depth 24 instead of 18 because the warm
hash let it keep going inside the same soft ceiling — 7.5 s total against 2.9 s
with the ladder off. Minimality of a ladder mate is **not** claimed: there is no
descent below the first rung that answers.

### Added — regression suite

- `scripts/selftest.py` over `tests/positions.tsv`, ten positions, about 30 s. The
  first three rows are mates the ordinary search prunes away and only the ladder
  finds; the rest cover a back-rank mate in one, two decisive-but-not-mating
  tactics, a position where the win is real but not forced, and two quiet openings
  that must not produce a false mate.
- `scripts/epdcheck.py` for external EPD suites, in `bm #N;` or `dm N;` form. It
  counts **three** outcomes rather than two: a mate at the published distance or
  shorter, a forced mate found further away, and no mate. The middle column is the
  one that answers "is there a forced win"; folding it into the failures
  understates the skill and folding it into the successes overstates it. It
  imports `parse_output` and `judge` from `selftest.py` rather than carrying a
  second copy — two parsers of the same output drift apart, and the copy is always
  the one that rots.

Two rules are written into `selftest.py` itself because both were learned the hard
way. It must never pass `--quick`, which drops the search to MultiPV 1 and thereby
bypasses exactly the multi-line stopping bugs the suite exists to catch — it uses
`--scan off` instead. And expectations use `mate<=N` rather than `mate=N`: a
shorter mate than the published one is a better answer, not a failure, and pinning
the exact number turns every genuine improvement into a red row. That is not
hypothetical — on one of the ten positions the ladder finds `Be6` mating in 4
where the plain search saw 6.

### Added — the version is now checked

`selftest.py` reads the version from `SKILL.md`'s frontmatter, `VERSION` in
`solve.py` and the top entry of this file, and **refuses to run when they
disagree**, exit code 2:

```
version mismatch, refusing to run:
  solve.py       2.3.0
  SKILL.md       2.1.9
  CHANGELOG.md   2.3.0
```

Verified by running it against a deliberately edited copy. A green suite against a
build nobody can name is worth very little, and this skill has already lost a
correctness fix to a build that never reached the installed copy.

### Verified

`selftest.py`: 10 passed, 0 failed, 30 s. All five scripts compile. The benchmark
position still answers `Rxg3+`, verdict *the win is forced, every reply loses (2)*
— the evaluation now prints around `+6.8` rather than `+6.0`, because the ladder
leaves the hash warm and the main search reaches a greater depth inside the same
ceiling.

---

## 2.2.0 — 2026-08-19

The release is about one thing: **the position was being read wrong, and the
checks meant to catch that did not.** In the run that prompted it, four pieces
were misplaced in a single diagram, three of the four errors produced a fully
legal position, and the engine answered each wrong position confidently. Most of
what follows is that fix.

### Fixed — the diagram-reading procedure

- **The second reading now uses a different traversal order.** The old procedure
  said to read the diagram twice. It did not say *how*, so both passes went rank
  by rank — and a second pass in the same order repeats the first pass's habits
  and reproduces its errors. The second reading is now **file-major**: files `a`
  through `h`, within each file ranks 1 up to 8, naming every piece with its
  square (`a2 B`, `b8 r`, `c1 b, c5 r`, …).

  This attacks the specific failure rather than adding effort. A rank-major
  reading assigns files *implicitly*, by counting a run of empty squares;
  miscount the run by one and a piece shifts sideways. A file-major reading names
  the file of every piece *explicitly*, so there is no run to miscount. The two
  FENs are then compared as strings: they agree or they do not, and there is
  nothing to interpret.

- **Removed the "each rank sums to 8" check, which was worthless.** The previous
  `references/reading-diagrams.md` recommended it as the main defence against a
  miscounted empty square. It defends against nothing: `python-chess` refuses to
  parse a rank that does not sum to eight, so every FEN that reaches the engine
  has already passed it. Verified — the parser rejects both a rank summing to 9
  and one summing to 7, before any check of ours runs. The file now says so
  explicitly, under the heading *"Each rank sums to 8" is not a check*, so the
  removal cannot be undone by someone re-deriving it as a good idea.

- **A file shift is now the first named blind spot of the legality check.**
  `SKILL.md` previously listed two things `STATUS_VALID` does not catch — a
  colour swap and an upside-down board. The most common error was missing.
  `3p2n1` and `3p3n` both describe a legal rank of eight squares, both keep the
  material count identical, and they put the knight on different files. Verified:
  both parse, both return `STATUS_VALID`, both count 18 pieces. Nothing inside
  the FEN can distinguish them; only the image can.

- **A legality failure now means re-reading the whole position, not patching one
  square.** The tempting repair is to nudge the offending piece one file, watch
  `STATUS_VALID` appear, and carry on. That is what happened: an `OPPOSITE_CHECK`
  was patched by moving a king, and three further shifted pieces survived into
  the answer, each of which changed the solution. A shift on one rank is evidence
  that the same miscounting habit ran on the other seven.

- **An illegal position is documented as a diagnostic, not merely an error.**
  `OPPOSITE_CHECK` usually means the FEN is wrong, but occasionally reveals the
  tactical point of the position — a pinned defender that cannot legally capture.
  Report what the check found; do not silently correct the FEN.

- **Material is counted per side, and the count is shown.** A colour swap leaves
  every other check satisfied and is invisible in the FEN string. `solve.py`
  prints per-side counts alongside the board so the comparison against the
  diagram costs nothing.

### Changed — when the reading is confirmed

- **Confirmation moved from before the search to before the verdict.** The old
  order held the engine back on the unstated assumption that searching is
  expensive. It is not: a typical position resolves in well under a second, so
  waiting bought nothing and delayed the user. What is expensive is a confidently
  stated wrong answer. Search first, confirm the reading, then speak.

- **Show the board every time; stop and wait only on cause.** A confirmation that
  fires on every position and is right most of the time trains the user to wave
  it through, at which point it costs a round trip and catches nothing. So the
  board is always displayed when the position came from an image, and the run
  stops for the user only when there is an actual reason to doubt: the two
  readings disagreed, legality failed on the first attempt, the diagram is
  cluttered or is a photograph of a physical board, the orientation was not
  settled by coordinate labels, or the material count looks wrong.

- **A user's correction triggers a full re-read.** When the user says a square is
  wrong, re-read the whole position rather than moving the one piece — same
  reasoning as the legality-failure rule above.

- **The recognizer is demoted from "the second reading" to "one possible second
  reading".** `img2fen.py` costs two to four minutes of TensorFlow install. The
  file-major re-read costs seconds and needs no dependencies, so it is the
  default second pass; TensorFlow goes in when the diagram is cluttered, when the
  reading is genuinely uncertain, or when the user asks for the automatic route.

### Added

- `README.md` — installation, usage, flags, layout, limitations. All example
  output copied from real runs rather than composed.
- `FAQ.md` — the comparison with `chess-best-move`, including where the other
  skill is the better choice, and the derivation of the winning-chances sigmoid.
- `CHANGELOG.md` — this file.
- `VERSION` in `solve.py`, `version:` in `SKILL.md`'s frontmatter, and
  `solve.py --version`. The three declarations are not machine-checked in this
  build; they were set together and must be changed together.

Two claims in the FAQ were corrected against real runs: the enumeration on the
benchmark position is full, not a sample of four defences — the move is a check,
Black has three legal replies, and `--full-max 8` fires automatically — and the
evaluation after `Kh8` is `+3.52`, not the `+3.76` carried over from an older run
at a different depth.

### Verified

Smoke-tested end to end on the benchmark position
`5rrk/1p1n3p/4pp1Q/3pP3/p2N3P/P2P2P1/4qPK1/1R5R b - - 0 1`: `Rxg3+`, `+6.03` at
depth 17 in 1.7 s of engine time, both replies enumerated, verdict *the win is
forced, every reply loses (2)*. All three scripts compile. An illegal FEN is
refused with `OPPOSITE_CHECK`. The three version declarations agree.

Output is English throughout: one string table per script, no selector, no flag
that switches it. Move notation is international regardless of what the answer is
written in — `Qc4+`, `Rxb8`, `Ne5` — because that is what `python-chess` emits,
what Lichess shows, and what pastes anywhere.

---

## 2.1.0 — 2026-08-18

### Fixed — the search discarded mates at the moment it found them

`Session.search()` was making stopping decisions on individual engine messages
rather than on completed iterations. With `MultiPV=2` Stockfish re-reports the
first line several times within one depth during aspiration-window re-searches,
so a counter on messages over-counts stability, and a proved mate arriving on
line 1 before line 2 was reported got thrown away in favour of the last complete
iteration — which held a different, non-mating move. Symptom on the reference
position `5k2/4pp2/5bp1/4q2p/3N4/2p1nQ1P/P1P5/K3R3 b`: `Qb8 +4.78` instead of
`Nxc2+`, mate in 4.

- Iterations are grouped by depth and committed only when the full
  `{1..multipv}` set has arrived: `cur` resets when `info['depth']` changes,
  accumulates by `info.get('multipv', 1)`, and moves to `done` only once
  `len(cur) >= want`. Lines taken from different iterations are not comparable
  with each other, and the code now says so.
- The stability streak advances on completed iterations, not on messages.
- The search exits on a proved mate as soon as `depth >= 2 * mate`.

`MultiPV=2` is what makes this bite: with two lines Stockfish reaches a mate far
later than with one — depth 21 against depth 15 on that position, roughly five
times slower. A large evaluation with no mate in a combinational position is
therefore worth re-checking with `--quick`.

---

## 2.0.0 — 2026-08-17

Renamed from `chess-position-analysis`.

### Changed

- **The timing journal became silent and unconditional.** `--start` prints
  nothing and runs on every analysis, because it cannot be started
  retroactively — asked "how long did that take" after the answer, there would
  otherwise be nothing to answer with. `--no-timing` became `--timing`: the
  breakdown is written always and printed only on request. The mechanics moved to
  `references/timing.md`, leaving `SKILL.md` a short section whose rule is *do not
  print the table unless the user asks*.
- **Notation is international.** The piece-letter translation rule was dropped
  from `SKILL.md`.
- **The description was rewritten to match what the skill actually claims.** The
  old one promised that all defences are refuted, contradicting the skill's own
  output categories, which distinguish *the win is forced, every reply loses* from
  *the win is not forced; these replies hold*. The word *verdict* was absent from
  the prose despite naming the skill; scope was widened to the non-puzzle
  questions the same pipeline answers.

### Added

- Move-gap threshold on a sigmoid winning-chances scale (`GAP_CHANCES = 0.05`,
  constant from Lichess) instead of a fixed centipawn margin: 30 centipawns
  decide the game at equality and are noise at plus seven.
- `--nodes` for reproducible runs. Node-limited results are identical regardless
  of machine load, time-limited ones are not — measured, depth 21 down to 18
  under artificial load, same answer, 1.1 s idle against 4.2 s loaded.

### Removed

- The duplicate hard-time check inside the convergence loop, already done by
  `Limit(time=...)`.

---

## Known gaps

- **Minimality of a mate is not claimed.** The ladder proves a mate exists at the
  distance it reports or shorter; it does not descend below the rung that
  answered. A `go mate n-1` descent after a hit would tighten it, at a second or
  so per step.
- **The ladder's cost is paid on every position, and it is not adaptive.** There
  is no cheap way to tell in advance that a position has no short mate, so the
  1.7 s is spent to find that out. Given what 2.3.1 established about the hash
  table, a cheaper ladder would also be a weaker one, so this is less obviously
  worth fixing than it looks.
- **The external suite is pinned by recipe, not bundled.** `SKILL.md` records the
  URL, the sha256 and the sample seed, so a run is reproducible, but nothing in
  the skill fails if the upstream file changes. Comparing across sessions means
  checking the hash first.
- **Ten of 24 on the reference sample find no mate at all.** That is the honest
  ceiling of a convergence-stopped search on composed problems at fifteen seconds
  a position, not a bug with a known fix. Raising `--budget` moves it; nothing
  else measured so far does.
