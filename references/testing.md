# Testing the skill

Everything here is for editing `chess-verdict`, never for answering a position.
`SKILL.md` carries no copy of it, because a session that is solving a puzzle has
no use for a regression baseline and pays for the words all the same.

## Reproducible runs

`--nodes N` is not for answering questions. It caps the search by node count instead of time and switches off both the convergence stop and the clock, so the result is bit-for-bit the same however loaded the machine is — which is what makes it possible to tell a change in the script from a change in the weather. It costs time to buy that. Use it when testing the skill, never when solving a position for someone.

## The suites

```bash
python3 scripts/solve.py --version                 # which build is mounted
python3 scripts/selftest.py                        # fixed set, about 50 s
python3 scripts/epdcheck.py suite.epd --limit 20   # an external EPD suite
python3 tests/test_stage.py                        # the timing journal, about 5 s
python3 tests/test_compare.py                      # the board detector, about 3 s
python3 tests/test_verdict.py                      # the verdict rule, instant
python3 tests/test_ladder.py                       # what the ladder may claim, instant
python3 tests/test_reader.py                       # the recognizer, offline, about 5 s
python3 tests/test_reader.py --sweep               # the 900-render held-out figure, about 1 min
```

`selftest.py` refuses to run when `SKILL.md`, `scripts/solve.py` and `CHANGELOG.md` disagree about the version — a green suite against a build nobody can name is worth very little. It runs `solve.py` with `--scan off` on most rows and `--scan full` on the three that cover the verdict branches, and it must never be given `--quick`: that drops the search to MultiPV 1 and bypasses exactly the multi-line stopping bugs the suite exists to catch.

`epdcheck.py` counts **three** outcomes, not two: a mate at the published distance or shorter, a forced mate found further away, and no mate at all. The middle column is the one that answers "is there a forced win"; folding it into the failures understates the skill and folding it into the successes overstates it. Add `--extra "--mate-probe 0"` to measure what the ladder is worth on the same suite.

What each `tests/` file is for, and why it is built the way it is, is in [below](#what-each-test-file-is-for).

### The matetrack suite

The published reference set. It is not bundled — fetch it, and pin the fetch so two runs are comparable:

```bash
curl -sSL -o /tmp/matetrack.epd \
  https://raw.githubusercontent.com/vondele/matetrack/master/matetrack.epd
sha256sum /tmp/matetrack.epd
# 8ba5712234ba0cb2a1f1b1934872d1d30ba5e01c80482844dccccd4bc2eefd72
python3 scripts/epdcheck.py /tmp/matetrack.epd --limit 24 --sample 20260820 --budget 15
```

6554 problems, mostly composed, weighted towards mate in 7 to 10. **Do not run the whole file** — at fifteen seconds a position it is a day's work. A fixed `--sample` seed with `--limit` is what makes two runs comparable; without the seed the numbers are noise. The reference figure for this build on that sample: **14 of 24 mates found, 12 of them at the published distance or shorter, 107 s.** With `--reprobe-step 0`: 14 found but only 8 at distance, 70 s. With `--mate-probe 0`: 5 of 24 — 6 since 2.28.0, which stopped the main search discarding a mate it had found, so the ladder is worth one position fewer than that gap suggests.

Re-measure the baseline on the machine in front of you before quoting a regression — a hardware difference reads exactly like a change in the script, and mistaking one for the other wastes an afternoon.

Two things in the file trip a careless parser, and `epdcheck.py` handles both: six problems are solved only by an en-passant capture, so the fourth EPD field must survive rather than being padded away, and twenty-six carry a negative distance, meaning mate *against* the side to move. A mate found for the wrong side is the opposite answer, not a near miss, so the sign is checked before the distance.

Use `--nodes` when comparing two versions of the script: it caps the search by node count, so the result is identical however loaded the machine is.

### What no suite measures

Both suites count mates found. Neither touches the failures in [Where the engine is the weak link](../SKILL.md#where-the-engine-is-the-weak-link), so a change that made any of them worse would show up nowhere. Until something covers them, these positions have to be checked by hand after editing `solve.py` — and the first two need a self-play run rather than an evaluation, playing sixty plies and recording the ply at which the halfmove clock first resets:

```
8/p7/kpP5/qrp1b3/rpP2b2/pP2b3/P7/K7 w - - 0 1              ; fortress, truth = draw, clock never resets
1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1                         ; Lucena, won, clock resets by about ply 20 (14, 18, 19 in three runs)
8/8/8/8/8/2k5/8/KBN5 w - - 0 1                             ; KBNK, won, no mate score expected
8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w - - 0 1               ; mate in 10, headline says +2.7
8/2P5/8/8/3r4/8/2K5/k7 w - - 0 1                           ; Saavedra, mate in 7, underpromotion
n6N/pr4p1/2ppp1Bk/P4p1P/r5PK/p6R/2PPP2N/8 w - - 0 1        ; known miss, mate in 8
2rn4/5p2/n1p1P2b/8/3kP1Pp/1P1Np3/1Kp1P3/1bB2N1B w - - 0 1  ; known miss, mate in 9
```


## What each test file is for

`tests/test_verdict.py` feeds constructed reply tables to `headline_understates()`
and `winning_mates()` rather than running a search, so no result depends on the
depth the engine happened to reach. That is the point: the rule it covers is
about *reporting* what the search found, and a test that had to search first
could be turned green by a lucky run on a position the rule gets wrong.

`tests/test_compare.py` builds synthetic diagrams with the board at a known
offset and asserts the detector lands within a few pixels of it. A detector has
no ground truth of its own — when it is wrong the sheet misaligns by half a
square and still looks plausible — so the fixtures have to carry the answer.
Two of them are regressions: the grey-label case that broke the first version,
and the monochrome board that the fix for it then deleted.

`tests/test_ladder.py` drives `probe_mate()` and `probe_shorter()` with a
scripted engine instead of Stockfish. The claim under test is how far the ladder
got before the budget stopped it, and on a real engine that is a fact about the
machine's speed on the day rather than about the code — the test would go green
or red with the load average. The scripted engine also records which rungs it
was asked, which is the only way to tell "asked and answered no" from "never
asked" from outside.

`tests/test_reader.py` is the first offline cover the recognizer has had.
It renders positions through `chess.svg` and `rsvg-convert`, reads them back
and compares against the FEN they came from, so the fixture carries its own
answer. The fixed cases are the 150 px render that was silently misread before
2.25.0 and the side-to-move handling; `--sweep` reruns the held-out set the
2.25.0 figures were measured on, seeded, so the numbers in the changelog can be
reproduced from a clean checkout. It skips, and says so, where `rsvg-convert`
or `onnxruntime` is missing.

`tests/test_stage.py` covers `stage.py` alone — the stop mark, its cancellation
by a later command, the bracket it closes, and `--at-last`. It uses real sleeps
rather than a mocked clock, because the bug it exists to catch was wall-clock
time being attributed to the wrong side of a mark, which a fake clock reproduces
just as happily as a real one.

`scripts/selftest.py` runs `solve.py` on `tests/positions.tsv`. Most rows use
`--scan off`, which keeps the suite near a minute; three use `--scan full`,
because until 2.22.0 the verdict branches — `v_incomplete`, `v_branch_mates`,
`v_holds`, `v_forced`, `v_forced_mates` and the `forced_verdict` handover to
`fifty_note_collapsed_forced` — had no end-to-end cover at all, only the two
helpers beneath them. The three rows cost nothing measurable: 17 rows in 51 s
before, 20 rows in 50 s after. (That count read 21 until 2.24.0, which was
simply wrong — a reminder that a number nobody re-derives drifts even in a
file about not letting numbers drift.) 2.24.0 adds two more, both refusals,
so they cost no search time. 2.27.0 adds the fortress row, a full enumeration
of about fifteen seconds.
