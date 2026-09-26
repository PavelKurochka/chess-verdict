<!-- Documentation for humans evaluating this skill.
     Not part of the skill instructions and not read at runtime:
     SKILL.md does not reference this file. -->

# FAQ — how does `chess-verdict` differ from `chess-best-move`?

*Compared against `chess-best-move` as of August 2026. That skill may have
changed since; the observations below are dated, not permanent.*

The closest neighbour to this skill is [`chess-best-move`](https://github.com/letta-ai/skills)
from the `letta-ai/skills` repository. The two overlap enough that the question
deserves an answer, and the answer is not "one is better" — they are built on
different beliefs about where a chess analysis actually goes wrong.

Everything presented below as a measurement comes from a real run or from a
default you can read in the source. Where a number is a single observation rather
than a benchmark, it says so.

---

## Short answer

`chess-best-move` is a **methodology document**: about two hundred lines of prose
telling an agent how to read a board out of an image without fooling itself, and
how to format the answer to a spec. It ships no code. Every operational decision —
engine settings, depth, when to stop, how many lines — is left to the agent to
invent on the spot.

`chess-verdict` is a **pipeline**: around 400 lines of `SKILL.md` over six
executable scripts (`solve.py`, `img2fen.py`, `stage.py`, `compare.py`,
`selftest.py`, `epdcheck.py`, `reader_eval.py`, ~3,300 lines together, plus a
vendored ONNX classifier and its Python port under `scripts/vendor/fenshot/`)
and two reference documents. The engine policy is code with defaults, not advice. What the
prose adds on top is a second concern the other skill never raises: how strong a
claim the result entitles you to make.

---

## Both were run on the same position. What happened?

Same diagram, same container class, same agent, one day apart.

Position: `Rb3rk1/6pp/8/2Q5/6b1/8/1q3PPP/4R1K1 w - - 0 1`, read from an image.

| | `chess-verdict` | `chess-best-move` |
|---|---|---|
| Answer | `Qc4+`, then `Ra2` | `Qc4+`, then `Ra2` |
| Engine time | ~1.7 s | ~11.5 min |
| Wall clock, end to end | ~83 s | ~14–15 min |
| Stockfish launches | 1 | 5 |
| Depth reported | 17, MultiPV 2 | 30 on the main line |
| Wasted work | none | first launch, 300 s, returned nothing |

Both got the move right. The whole difference is in what it cost.

The first `chess-best-move` launch asked for depth 40 with four lines and no time
cap. On a position with two queens that did not finish inside the five-minute tool
timeout, so it produced nothing at all — more than a third of the session spent
for zero output. The remaining four launches each started a cold engine with an
empty hash table and re-derived work the previous one had already done.

Nothing in `chess-best-move` caused that, and nothing in it prevented it either.
The document says "consider using Stockfish for evaluation" and stops. With no
stated notion of what *enough* looks like, an agent reaches for numbers that sound
thorough — depth 40, MultiPV 4, five minutes — because thoroughness is the only
axis the document offers.

**Caveat, stated plainly:** one position, one run each. Treat the ratio as an
illustration of a mechanism, not as a measured speedup.

---

## What is the single biggest mechanical difference?

The stopping criterion.

`solve.py` reads the engine's iterations as they arrive over UCI and returns as
soon as the best move stops changing — once it has held for `--stable` iterations
(default 5) past `--min-depth` (default 18), or the moment a mate is proved.
`--time` (default 5 s, hard ceiling three times that) sits on top as a soft cap,
not as the normal exit. `--depth` defaults to 30 and is described in the source as
a *ceiling, rarely reached*. A typical position resolves in **2–10 seconds**.

That works because of an empirical fact `SKILL.md` states outright: on a single
core Stockfish reaches depth 18–20 in one to two seconds and depth 30 in about
twenty, and the answer to a tactic is normally settled by depth 12 and only
refined afterwards. Time past that point buys decimal places, not moves.

There is a second exit as well: `--win` (default 400 cp). Once the advantage is
decisive, deeper calculation cannot change the verdict, so it stops.

`chess-best-move` has no concept of stopping. Depth and time are chosen fresh on
every run by whichever agent is holding the document.

---

## What else is in the engine policy that `chess-best-move` leaves open?

**One invocation, not several.** A single `solve.py` run yields the best move with
its evaluation and depth, the second-best *at the same depth*, the main line, and
the defender's best replies with their own evaluations and lines. Internally the
searches share a game key and skip `ucinewgame`, so the hash survives from the
main search into the defence search. `SKILL.md` states the rule flatly: do not run
the script twice — a second run starts a cold engine with an empty table and
repeats the entire first search. If more depth is genuinely wanted, raise `--time`
on the *first* run.

**Small hash, deliberately.** 64 MB per core. This is counter-intuitive and was
measured: Stockfish zeroes the hash table when a search starts, and on a gigabyte
that alone is about three seconds of dead time per launch — more than the useful
calculation. `chess-best-move` says nothing about hash, and the sensible-looking
guess is exactly the wrong one. `references/timing.md` closes the loop: engine
startup above one second in the breakdown *means* the hash is too large.

**Tiered budgets.** The main search, the defence search and per-reply scoring get
different allowances — `--time` 5 s, `--defence-time` 4 s, `--reply-time` 2 s with
`--reply-depth` 16 against the main line's minimum of 18. Replies are deliberately
searched shallower, because they exist to illustrate the win, not to establish it.

**MultiPV kept narrow.** The second-best move comes out of the same `MultiPV=2`
search as the best move, so both numbers share a depth and the gap between them
means something. Defences come from one further search with `MultiPV` set to
`--defences` (default 4). `SKILL.md` explains why the obvious alternative is
wrong: MultiPV suppresses the cutoffs that make the search fast, so scoring thirty
replies one by one costs about as much as thirty full searches — and re-derives
the same number thirty times, because *the evaluation after the best move already
assumes the defender's best reply*.

**Full enumeration only where it is cheap.** All replies are scored when there are
at most `--full-max` (default 8) of them, or when a mate has been found — in a
mating net the defender usually has two or three moves, the list costs under a
second, and then the list itself is the proof. `--scan full` forces it anywhere.

**A named list of things that are slow.** `SKILL.md` carries a section titled *What
makes this slow — do not do it*, and every entry is something that has actually
cost minutes: background deep runs with `nohup`, raising `--budget` to hundreds of
seconds "to be safe", driving the engine by hand through `printf | stockfish` with
a fixed `sleep`, installing the recognizer runtime when no image needs recognizing, running a
command outside the timing wrapper.

---

## Both skills read boards from images. How do the approaches differ?

This is where `chess-best-move` is genuinely strong, and worth reading on its own
terms.

Its perception procedure is more explicit than this skill's: detect the 8×8 grid,
classify all 64 squares individually for colour *and* piece type, validate counts
(≤32 pieces, one king per side, ≤8 pawns and ≤2 rooks plus promotions), render the
reconstructed FEN back to a diagram and compare against the original. Its *Common
Pitfalls* section is good writing about self-deception: pattern-matching to famous
puzzles instead of analysing the image, confirmation bias from two recognised
squares ("pieces on h5 and f7, therefore Legal's Mate"), and circular verification —
assuming a position, testing a move against the assumption, concluding the move is
correct.

`chess-verdict` shares the premise. Its own opening line is *the engine is never
the weak link; reading the position is* — a single misplaced piece produces a
syntactically perfect FEN, a confident evaluation, and a completely wrong answer.

The differences are in the route, and in what gets checked afterwards.

**Route.** `chess-best-move` treats programmatic detection as the primary path and
suggests building it — OpenCV, contour detection, template matching, debug
visualisations. `chess-verdict` makes reading the diagram directly, as it arrives
in the conversation, the normal path, because on a clean diagram it is both faster
and more reliable. `img2fen.py` is a *cross-check* on that reading. Through 2.17.0 the TensorFlow
stack behind it cost two to four minutes to install; since 2.18.0 the model ships
with the skill and `onnxruntime` installs in seconds, so the cost argument is gone
and only the ordering argument remains — run it when the diagram is cluttered, the
reading is genuinely uncertain, or the user asks for the automatic route. For a clear diagram
the cheaper second reading is a manual re-read in file-major order, compared
against the first; `solve.py` then prints the resulting board and per-side
material counts so the reader can check them against the diagram without leaving
the conversation. Two browser fallbacks are named for when
the recognizer fails or cannot be installed: [fenshot](https://fenshot.com/), which
runs entirely client-side and uploads nothing, and
[Chessputzer](https://www.ocf.berkeley.edu/~abhishek/putz), good on book diagrams —
it wants the board border *included* and cropped tightly, the opposite of what
`img2fen.py` needs.

**When the recognizer does run, it degrades in a stated way.** `img2fen.py`
locates the board itself — gradient profiles, arithmetic sequences of peaks for
the grid lines, checkerboard correlation to choose between candidates — so a
frame, a caption or a whole page around the diagram is not a problem and there is
no margin ladder to tune. A reading whose weakest square scores below `0.75` is
withheld rather than returned. The recognizer still needs a flat 2D diagram and is
unreliable on photographs of physical boards taken at an angle.

**The gate now covers the piece-set failure, which it did not before.** Through
2.17.0 the network had no way to say "I do not know": across twenty piece sets it
read six reliably, refused eight, and on the rest returned wrong positions at a
softmax up to 1.000 — confidently, so no threshold could filter them. The
classifier used since 2.18.0 drops its confidence instead, and on the same
twenty-set stand reads 200 of 200 with no silent wrong answers, against 89 correct
and 46 silent wrong for its predecessor. The material count below still catches
what the gate does not: the gate is a filter on how sure the classifier was, never
a proof that it was right.

**What legality does not catch.** Both skills validate the FEN with
`python-chess`. `chess-verdict` adds the point that this is a weak check. It
catches a missing king, a pawn on the first rank, an impossible check — but none
of the three errors that actually produce nonsense. A piece read in the wrong
colour leaves a perfectly `STATUS_VALID` position; this has happened with
`img2fen.py`, and it surfaces only in a per-side material count against the
diagram, which `solve.py` now prints. A board read from the wrong side is legal
too, merely rotated 180°. And a *file shift* — a run of empty squares miscounted
by one — is the commonest of the three and the one with no defence inside the
string at all: `3p2n1` and `3p3n` are both legal ranks of eight, and they put the
knight on different files.

That last one is worth dwelling on, because the obvious guard against it does not
work. "Each rank sums to eight" reads like a check and is not one: `python-chess`
refuses to parse a rank that does not sum to eight, so every FEN reaching the
engine has already passed it. An earlier version of `reading-diagrams.md`
recommended it as the main defence against a miscounted empty square; it has been
replaced by a second reading of the diagram in a different traversal order —
file by file rather than rank by rank — because a file-major pass names the file
of every piece explicitly and so has no run of empty squares to miscount. This is
the point where `chess-best-move`'s per-square procedure has the same instinct:
classify all 64 squares individually rather than compressing as you go.

There is a further note worth having: `OPPOSITE_CHECK` is a diagnostic rather
than an error, because it occasionally reveals the tactical point of the position
— a pinned defender that cannot legally capture — rather than a corrupt FEN. The
instruction is to report what the check found, not to silently repair the FEN.
The stronger form of that rule, added after a run where it was violated: a
legality failure means re-reading the whole position, because a shift on one rank
is evidence the same miscounting ran on the other seven. Patching the single
offending square makes `STATUS_VALID` appear while leaving the rest of the errors
in place.

**The fields after the board.** `references/reading-diagrams.md` covers the FEN
tail, which `chess-best-move` does not touch at all: `-` is the safe castling
default for a middlegame or endgame diagram, and `KQkq` should be written only
when the rooks and king are demonstrably home and there is reason to think they
have not moved — because *a wrong castling right lets the engine find a move that
does not exist*. That failure is invisible in every check above.

---

## Board orientation gets a whole section here. Why?

Because it silently produced a wrong answer, and nothing downstream caught it.

`chess-best-move` covers orientation in one clause under grid detection:
*determine board orientation (which corner is a1)*. Correct, and insufficient,
because the failure is invisible. A diagram drawn from Black's side and read as
normal gives a position that is legal, plausible, and rotated 180° — every square
carries the wrong name, `a8` holds what actually stands on `h1`, and the engine
returns a confident evaluation of the wrong position.

`chess-verdict` therefore settles it before reading a single piece:

- **Read the coordinate labels first.** Files `a→h` left to right with ranks `8→1`
  top to bottom is the normal view. Files `h→a` with ranks `1→8` means the board is
  drawn from Black's side.
- **Reading by hand, reverse the whole sequence.** Write out all 64 squares in
  image order, then reverse the entire list before cutting it into ranks — the
  reversal *is* the 180° rotation. `reading-diagrams.md` also gives the shortcut
  that is easier by eye: read the image backwards, bottom-right square first, then
  right to left and upward, which produces FEN order directly. `img2fen.py` does
  the same with `--view black`.
- **The side to move follows.** Diagrams are drawn from the point of view of the
  side that has to act, so a Black-view board is Black to move by default. This is
  a convention rather than a law, so it yields to anything explicit — the user's
  statement, a caption, or an arrow marking the move just played (which means the
  turn belongs to the *other* side). What must never happen is the turn being
  guessed from the position itself: a tactic solved for the wrong side gives a
  confident answer to a question nobody asked.
- **No labels at all:** the pawns decide, and `solve.py` runs the test on every FEN
  it is given. The implementation is honest about its own limits — it requires at
  least three pawns a side and fires only on a clear discrepancy (a mean-rank
  difference above half a rank), so it stays silent in symmetric structures and
  pawnless endgames. The skill's own words: treat it as a net, not as a check. If
  neither labels nor pawns settle it and the answer depends on which side is
  which, ask.

---

## What does `chess-verdict` do that `chess-best-move` does not attempt at all?

Two things, and they are why the skill is called *verdict* rather than *best move*.

### 1. It measures the gap to the second-best move on a calibrated scale

Knowing the best move is not the same as knowing it is the *only* move.
`chess-best-move` asks the agent to return all winning moves when the task says
multiple solutions exist, but offers no way to decide whether a second move is
genuinely equal or merely close enough to look equal at the depth reached.

Centipawns cannot answer that, because thirty centipawns decide the game at
equality and are noise at +7.00. A fixed centipawn threshold calls the same number
meaningful in one position and meaningless in another. `solve.py` converts both
evaluations with the Lichess sigmoid — `2 / (1 + exp(-0.00368208 · cp)) - 1`, a
constant fitted on real game outcomes — and calls the difference a `lead` only
above `GAP_CHANCES = 0.05`: about 27 centipawns at equality, about 43 at +4.00,
about 90 at +7.00, about 550 at +15.00.

Mates bypass the scale entirely, because in chances a mate and a twenty-pawn
advantage are the same number, and for a puzzle they are not. Each mate case gets
its own label instead of a number, including the two asymmetric ones — the second
move mating as well, and the second move *walking into* mate.

The script labels its own output — `lead`, `difference … within search noise`,
`only this move mates`, `the second move mates too`, `decisive gap: the second
move loses to mate` — and `SKILL.md` instructs the writer to take the label as
given rather than eyeballing the centipawns. `difference +3.00 … within search
noise` is not a contradiction; it is what three pawns are worth in a position
already won by fifteen. When the label says the two are equivalent, the answer
must say plainly that both are playable and the engine's ordering at this depth
means nothing.

On the head-to-head position this produced a usable fact: `Qc4+` at +3.49 against
`Rxb8` at +0.05, a gap of +3.44 at equal depth. The solution is unique — a claim
the tool earned rather than assumed.

### 2. It states how far the win was actually proved

`chess-best-move`'s verification checklist ends at *move(s) achieve the stated
objective (checkmate, etc.)*. Binary — which fits a task arriving with an answer
key. Most real positions do not.

`chess-verdict` distinguishes three outcomes and forbids upgrading between them. A
top-N sample of defences supports only the claim that the advantage *survives the
defender's best try*. Full enumeration — automatic in a mating net or under
`--full-max`, forced with `--scan full` — supports the stronger claim that every
defence has been refuted one by one. And if enumeration left replies unscored,
`solve.py` marks them `not scored` and says the proof is incomplete; so must the
answer.

On the benchmark position that mattered, and the enumeration there was full
rather than sampled: `Qc4+` is check, Black has three legal answers, so all three
were scored automatically. Two lose at once — `Rf7` to `Re8#`, `Be6` to `Qxe6+` —
but `Kh8` holds at +3.52. The run therefore ends in *the win is not forced; these
replies hold: Kh8*, where a position that does go through ends in *the win is
forced, every reply loses*. The honest verdict is that White wins a piece, not
that White mates. A tool that only reports "best move: `Qc4+`" cannot make that
distinction, and an agent under pressure to sound decisive will round it the wrong
way. `SKILL.md` closes that door explicitly: do not round a forced mate down to
"winning" or inflate a small advantage; `mate in 19` means a forced mate exists but
is long, and should be reported as exactly that.

---

## What about the output?

They are aimed at different readers, and it shows in the first and last steps of
each document.

`chess-best-move` opens by asking what output format the *task* requires —
space-separated or newline, `g2g4` versus `Ng4` versus `g4` — and closes by asking
the agent to match it exactly. That is an evaluation-harness shape, and reasonable
for benchmark work.

`chess-verdict` closes on explanation for a human: the move with its mechanism in
one sentence (a pinned defender, an overloaded piece, a mating net), then the
defender's tries and why each fails, then the evaluation with the label the script
assigned it, then — if relevant — which earlier move created the problem, then the
Lichess link so the reader can replay the line without trusting anyone.
*Give the idea, not a transcript.*

Ahead of all that, when the position came from an image, comes the board as read.
Whether to *stop and wait* for the reader to confirm it is left as a judgement
rather than a rule, and the document says why in both directions: never stopping
is how a misread position reaches a confident answer, but stopping on every
position trains the reader to wave the confirmation through, at which point it
costs a round trip and catches nothing. The gate fires on cause — the two
readings disagreed, legality failed, the diagram is cluttered or photographed,
orientation was not settled by labels — and otherwise the board is simply shown
alongside the verdict. The confirmation sits before the *verdict* rather than
before the *search*, which is the opposite of where it was first placed: the
search costs well under a second, so holding it back delays the reader and buys
nothing.

One thing that matters in multilingual use: the answer is written in the user's
language, but **move notation stays international in every language** — `Qc4+`,
`Rxb8`, `Ne5` — because that is what `python-chess` emits, what Lichess shows, and
what pastes anywhere. Local piece letters are used only on request, and the
document warns about the collisions those mappings tend to contain. The scripts
themselves print English and are not translated: their output is material for the
assistant to work from rather than text to quote, and the parts that carry the
meaning — squares, moves, evaluations — are language-independent already.

---

## Why is there a timing script?

Because when a run is slow the useful question is *which stage*, and guessing gets
it wrong.

`stage.py` journals the whole chain — installs, diagram reading, every `solve.py`
run with its internal stages — and every command goes through the wrapper. It
cannot be started retroactively, so it records on every analysis. The table is
**not printed unless the user asks**; a ten-row breakdown after every puzzle is
noise.

The documented example is the argument in one glance:

```
  install engine                                              6.1 s   18%
  install python-chess                                        2.5 s    7%
  reading the diagram from the image, no img2fen.py          14.8 s   43%
  solving the position (solve.py)                             2.6 s    8%
      engine startup: 1 thread(s), hash 64 MB                 0.5 s
      main search to depth 17, MultiPV 2                      1.7 s
      enumerating all replies: 2 replies, of which searched 2 0.3 s
  other: gaps not covered by a measurement                    8.4 s   24%
  TOTAL                                                      34.4 s
```

The engine's actual thinking is 1.7 seconds out of 34.4 — five percent. Tuning
`--time` would improve nothing here; reading the diagram and the assistant's own
composing time are the whole story. That is the finding the instrumentation
exists to deliver, and it is why the skill's first slowness rule is *check the
stage breakdown before changing any flag*.

Three details make the table trustworthy rather than decorative. Unmeasured time
cannot vanish: `--report` measures from `--start` to `--stop`, subtracts what is
accounted for, and dumps the remainder into `other`, so a step nobody bracketed
becomes anonymous rather than invisible. The window has to be closed, or the
remainder swallows the table: until 2.11.0 there was no `--stop` and the span ran
to the moment of printing, which — printing being on request — meant the wait for
that request was counted as analysis, once turning fifteen seconds of work into a
reported 549 s. And `references/timing.md` supplies the reading
key — time in **main search** is the only line that buys accuracy; **engine
startup** over a second means the hash is too large; a large **defences** or
**enumerating all replies** means the reply work should be narrowed; a large
**importing python-chess** means the container is cold, not that the position is
hard.

`chess-best-move`'s instrumentation is debug images — grid lines, square
boundaries, labelled piece locations. That is instrumentation for perception,
which is what it believes the problem is. Neither skill's instrumentation
substitutes for the other's.

There is also a reproducibility mode. `--nodes N` caps the search by node count
and switches off both the convergence stop and the clock, so the result is
bit-for-bit identical however loaded the machine is. It costs time to buy that:
measured, the same position took 1.1 s idle and 4.2 s under load with an identical
answer, where the normal mode took 0.2 s and 1.3 s. It exists to tell a change in
the script from a change in the weather when editing `solve.py` — the source
comment calls it *a mode for testing the skill, not for answering*.

---

## Does it handle anything besides puzzles?

Yes, and `chess-best-move` by its own framing does not. Its scope is finding the
best move; `chess-verdict` routes other question types through the same pipeline:
`--quick` plus the main plans for "who stands better and why"; two `--quick` runs
on the positions before and after for "was that a mistake"; and for openings, an
explicit warning that the engine's preference is not the same thing as theory.

Quiet and endgame positions get their own caveat, because that is where
evaluations drift with depth: raise `--time` and `--min-depth` together, and name
the depth the number came from.

Endgames get a second one since 2.10.0, and it is not about depth. At seven men
or fewer the position is solved and the engine is not the tool — nothing here
installs tablebases, so K+B+N against a bare king is a forced mate in at most 33
and reads about `+2.6` at any depth. The run prints a `tablebase.lichess.ovh`
query URL for the user to open, and says the ending should be named rather than
quoted as a number.

---

## Where is `chess-best-move` the better choice?

Genuinely, and not as a courtesy:

- **You want a document, not a runtime.** `chess-best-move` is portable prose with
  no dependencies. `chess-verdict`'s scripts assume a Linux environment with
  `apt`, `pip`, and Stockfish at `/usr/games/stockfish` (overridable via
  `$STOCKFISH`).
- **You are building the vision yourself.** Its per-square procedure, count
  validation, and debug-visualisation discipline are a better starting point than
  "read it off the image" if you actually intend to write a detector.
- **You are running against an eval harness.** Output-format matching and "return
  all winning moves" are first-class requirements there, and it treats them as
  such.
- **Your positions come with an answer key.** The binary check suffices, and the
  calibrated hedging `chess-verdict` insists on is overhead.

And where `chess-verdict` is weaker than the above might suggest:

- **`--defences 4` is a sample, not a proof.** In a quiet position with many
  playable defences, the default run supports only the weaker claim. Stated rather
  than hidden, but still a limitation.
- **The second-best move is reported, not refuted.** `solve.py` tells you `Rxb8`
  scores +0.05 against `Qc4+`'s +3.49; it does not automatically show the line
  proving it. `SKILL.md` forbids inventing one from the gap and points at the
  extra `--quick` run instead, but the run is manual. In the `chess-best-move` run, roughly two minutes of extra search
  bought exactly that — the demonstration that `1.Re8??` loses to `Qb1+ Qc1 Qxc1+
  Re1 Qxe1#`, and that `1.Rxb8?!` only equalises because the check on c4 has to
  come *before* the exchange or a2 is left undefended. Slow, but not worthless.
- **The convergence stop is tuned for tactics.** In quiet and endgame positions the
  remedy is manual — raise `--time` and `--min-depth` and name the depth — which is
  honest but not automatic. And depth is not always the missing ingredient: on
  `8/8/p1p5/1p5p/1P5p/8/PPP2K1p/4R1rk w` the headline reads `+2.67` in a position
  that is a forced mate in 10, and no combination of time, depth or mate-ladder
  settings reaches it. Since 2.10.0 the run at least refuses to print a verdict
  contradicting its own reply list, which is what it used to do there.
- **The engine's own blind spots are reported, not solved.** A fortress is
  evaluated as if it could be converted: the Penrose position reads `-11.25` for a
  side that cannot make progress. 2.10.0 adds a fifty-move probe and a `--playout`
  check that make the failure visible in the output; neither turns the wrong
  number into a right one, and the probe is one-sided — a won rook ending fails it
  exactly as a fortress does.
- **The recognizer is an optional dependency and still fallible.** Seconds to
  install since 2.18.0 rather than minutes, but unreliable on angled photographs
  of physical boards, and capable of a colour swap that passes every legality
  check.
- **Everything measured about the recognizer is measured on rendered diagrams.**
  The twenty-piece-set stand behind `reader_eval.py` draws its boards; so did the
  suites behind 2.14.0 and 2.14.1. What speaks for photographs is nine fixtures
  from the fenshot repository. The datasets that would settle it — ChessReD,
  koryakin's "Chess Positions" — sit behind `data.4tu.nl`, `kaggle.com` and
  `storage.googleapis.com`, all of which the container's egress policy blocks.
- **The confidence gate has one local measurement, not a calibration.** 0.70
  came from upstream, measured against a different rasteriser; the same fixture
  scores 0.893 there and 0.764 under this pipeline's Pillow. 2.24.0 moved it to
  0.75 on a round-trip sweep — sixteen positions rendered at fifteen scales, 240
  readings — where 0.70 let one wrong, legal, unwarned reading through and 0.75
  did not, at a cost of four correct readings in 209. That is one instance, on
  one piece set, rasterised one way. It is not the calibration, which still needs
  the datasets above.

---

## One-line summary

`chess-best-move` answers *what is the best move, and did I read the board right*.
`chess-verdict` answers *what is the best move, is it the only one, how strongly
was that shown, and where did the time go* — and it answers in seconds, because
the engine policy is compiled into a script with defaults instead of re-invented
on every run.

---

## Sources

- [`letta-ai/skills` — repository](https://github.com/letta-ai/skills)
- [README.md](README.md) — install, usage and flags for this skill
- [`chess-best-move` — full SKILL.md text](https://agentskills.so/skills/letta-ai-skills-chess-best-move)
- [Lichess Accuracy metric](https://lichess.org/page/accuracy) — origin of the constant `0.00368208`
- [fenshot](https://fenshot.com/) — client-side diagram reader
- [Chessputzer](https://www.ocf.berkeley.edu/~abhishek/putz) — diagram reader for book positions
