---
name: chess-verdict
license: GPL-3.0-or-later
metadata:
  version: "2.31.0"
description: >-
  Deliver a verdict on a chess position with Stockfish: read the position from a
  diagram image or a FEN string, confirm the reading is legal and the right way
  up, then give the best move, the line behind it, why the defender's best tries
  fail, and whether the win is a forced mate and of what length. Use it whenever
  a concrete position is on the table: a photo or screenshot of a board, a FEN
  string, or a puzzle ("find the win", "what should White play", "is this
  winning?", "is there a mate here?"). It covers positions from a game or a
  book, requests to check an engine evaluation, and questions with no puzzle
  framing at all — who stands better and why, whether a move was a mistake,
  whether a sacrifice is sound — even if the user never mentions Stockfish, FEN,
  or an engine. It also reports how far anything short of mate has been proved.
  Not for chess questions with no position on the table: rules, history, opening
  repertoire, player biographies.
---

# Chess verdict

*A position in, a verdict out: the move, the line behind it, and how far it was actually proved.*

**The version is `metadata.version` in the frontmatter above.** It must match `VERSION` in `scripts/solve.py` and the top entry of `CHANGELOG.md`; `python3 scripts/solve.py --version` says which build is mounted, and `selftest.py` refuses to run when the three disagree. The number is deliberately not repeated here.

A picture or a FEN goes in; what comes back has been checked twice — once for whether the board was read correctly, once by the engine. The verdict states its own strength: a forced mate is called a forced mate, an advantage that merely survives the defender's best try is called that and no more.

After the one-time setup nothing here needs the network, with one optional exception. Engine, recognizer and search all run locally; at seven pieces or fewer `solve.py` also asks the Lichess tablebase for the exact result, which works only if the user has put `tablebase.lichess.ovh` on the sandbox allowlist (see [Exact endgames](#exact-endgames-the-one-network-setting)). Without it everything else works as before.

**Why the steps are in this order.** In almost every position the engine is not the weak link; reading the position is. A single misplaced piece produces a syntactically perfect FEN, a confident evaluation, and a completely wrong answer. So the position gets read twice, by two different procedures, and the two readings are compared. The exceptions are narrow and recognisable before the answer is written — see [Where the engine is the weak link](#where-the-engine-is-the-weak-link).

**Confirm before the verdict, not before the search.** Searching is cheap; a confidently stated wrong answer is not. Search first, then confirm the reading, then speak.

**The engine part costs seconds, not minutes.** `solve.py` stops on convergence rather than on the clock, one invocation covers best move, second-best and defences, and a normal run takes **2–10 seconds**. If a run is taking minutes, something is wrong with how it was invoked, not with the position.

## Where the engine is the weak link

Three kinds of position make Stockfish state a number confidently and wrongly, and depth fixes none of them. All three can be spotted from the board before the verdict is written. The measurements behind this section are in [rationale](references/rationale.md#where-the-engine-is-the-weak-link).

**Fortresses.** Material says one thing and the position is a draw. A blocked structure is not by itself the trigger — an extra queen behind sixteen locked pawns still mates in 11. What matters is whether progress requires a capture or a pawn move that cannot be forced, which is what the probe below measures.

**Theoretically decided endgames.** Nothing here installs Syzygy files. K+B+N against a bare king is a forced mate in at most 33 and reports about `+2.6` at any depth reached in a minute. Below eight pieces `solve.py` asks the Lichess tablebase instead, when the sandbox may reach it; when it may not, name the ending and hand over the tablebase link (step 4).

**The halfmove clock, which is part of the position.** The same K+B+N placement with `90` in the fifth field evaluates `0.00` instead of `+2.57`, because the engine applies the fifty-move rule inside its search. Screenshots carry no clock, published FENs pad it to `0`, and `img2fen.py` writes `0` there unconditionally. The castling rights beside it *are* read from the home squares; the clock is still a constant, not a reading.

### The 50-move probe, and what it does not prove

`solve.py` re-evaluates the same placement with the halfmove clock at 90 — ten plies before a draw — and prints one line about it, inside the same run. It fires by itself at seven men or fewer and on any decisive evaluation for either side, costs about two seconds, and is controlled by `--fifty-probe {auto,on,off}`, `--fifty-clock` and `--fifty-seconds`.

**A collapsed probe is one-sided evidence.** An advantage that survives it is real and can be reported as a number. An advantage that collapses has only failed to show progress in ten plies — which is true of a fortress, true of a mate in 33 with no pawn moves in it, and equally true of a textbook won rook ending. A collapse is a reason to look further; it is never a verdict of "drawn", and passing it on as one replaces one confident wrong answer with another.

**A collapsed probe does not outrank a proof — and a list of centipawn scores is not one.** When every reply in a complete list was mated, the win is proved and the probe has only failed to show progress in ten plies, which is what a long win looks like; the script says so, and the answer reports the win and notes that the fifty-move count matters if the position came from a game. When the replies are decisive only in centipawns, the script says `an evaluation, not a proof`: that list is the same kind of number the probe has just contradicted, and `--playout` decides. ([The fortress behind this](references/rationale.md#the-verdict).)

**What separates the two cases is where the clock first resets.** `--playout 60` plays the position out against itself and reports the ply at which the halfmove counter first reset — on Lucena between ply 14 and 19, on a fortress never. About twenty seconds, so it is off by default and worth running exactly when the probe has collapsed; raise `--budget` with it. Read how it ended: cut short by the budget proves nothing; a claimable draw with no reset is the fortress signature; running out of plies with no reset and no repetition has seen nothing yet — rerun with `--playout 100`, the fifty-move rule's own horizon.

## Reading the files of this skill

Open `SKILL.md` once with `view`. That single line in the transcript is the activation signal and is worth keeping. Read everything else in the directory `SKILL.md` was opened from — references, tests, the scripts themselves — with `bash` (`sed -n`, `cat`, `grep`) instead. Every `view` on a path under `/mnt/skills` emits another identical *Loaded skill chess-verdict* line, and a column of those says nothing about which build is running. The line that says that is the banner `solve.py` and `img2fen.py` print first, which is why they print it. ([What was measured](references/rationale.md#reading-the-files-of-this-skill).)

## Setup

```bash
python3 scripts/stage.py --start
python3 scripts/stage.py "install engine" -- apt-get install -y stockfish
python3 scripts/stage.py "install python-chess" -- pip install chess --break-system-packages --use-pep517 -q
python3 scripts/stage.py "install rasteriser" -- apt-get install -y librsvg2-bin
```

About fifteen seconds together. The installs are kept apart deliberately: in one command the download and the unpacking merge into a single unreadable number.

**The third line is worth its three seconds:** it turns the diagram into a PNG, which the assistant can open and an SVG it cannot. `pip install cairosvg` does the same; ImageMagick does not. Without either, `solve.py` writes an SVG and everything else works.

The first line starts the timing journal. From then on every command goes through the wrapper: `python3 scripts/stage.py "<label>" -- <command>`. It is closed by `python3 scripts/stage.py --stop` after the last command of the analysis — see [Timing](#timing). **The timing table is not printed unless the user asks for it.**

**Only if a diagram came from an image**, add what `compare.py` in step 4 needs:

```bash
python3 scripts/stage.py "install imaging" -- pip install pillow numpy --break-system-packages -q
```

Usually already present, in which case this costs a second and says so. It has nothing to do with recognition — `compare.py` only crops and composes.

**Only if a diagram image has to be recognized**, add the reader's runtime:

```bash
python3 scripts/stage.py "install recognizer" -- pip install onnxruntime pillow numpy --break-system-packages -q
```

About 54 MB and a few seconds; the model itself ships with the skill at 1.3 MB. This is cheap now, but it is still a *second* reading rather than a replacement for the first: reading the position straight off the image is the normal path.

### Exact endgames: the one network setting

At seven pieces or fewer the exact answer is a tablebase lookup, and `solve.py` makes it against `tablebase.lichess.ovh`. Whether the sandbox may reach that host is the **user's** setting, not something the assistant can change: *Domain allowlist → Additional allowed domains*, where the user adds exactly `tablebase.lichess.ovh` (on Team and Enterprise plans an organisation admin controls this). The change may take effect only in a new chat. Nothing else this skill does needs a domain added — not `lichess.org`, not a wildcard — so do not suggest more than that one host.

`solve.py` reports one of three things on its own, right after the board link:

- `Tablebase (Lichess Syzygy, exact): …` — the answer. See step 4 for how to report it.
- `… this sandbox's network allowlist refuses tablebase.lichess.ovh …` — the setting is missing. Tell the user once, in one sentence, which host to add and where, then carry on with the engine as below. Do not repeat it on every position in the same conversation.
- `… the tablebase did not answer (…)` — a timeout, a rate limit, an outage. Not a setting: do not send the user to their settings; hand over the link.

`--tablebase off` skips the query and prints only the link, for runs that must not touch the network.

If the network blocks the recognizer's install, say so and read the position straight off the image; the engine part works regardless.

**If python-chess itself will not install, nothing here runs.** Say so plainly, and do not analyse the position by hand as though the engine had. (`--use-pep517` is in the setup line because python-chess 1.11 ships as source only, and some images cannot build it without it.)

**`STOCKFISH STOPPED ON THIS POSITION` is the same case for one position** (newer Stockfish refuses e.g. nine pawns a side): pass on its reason, say no verdict was computed, and do not analyse by hand.

## Step 1 — Get a FEN

**Reading the position straight off the image** — no recognizer process, just the diagram as it arrives in the conversation — is usually faster and more reliable than `img2fen.py`, and is the normal path. It has no command of its own, so bracket it: `--begin "reading the diagram from the image, no img2fen.py"` before looking at the image, `--end` once **both** readings are written down and compared.

**From an image, with the recognizer:**

```bash
python3 scripts/stage.py "reading the diagram (img2fen.py)" -- python3 scripts/img2fen.py board.jpg b
# second argument: w or b, whose turn it is
# --view black when the diagram is drawn from Black's side — see below
```

**Without the second argument a normal-view reading prints two FENs, one per side to move**, unless a king in check settles it. A diagram in the normal orientation does not say whose move it is, so take the turn from the caption, the question or the user, and ask when nothing says. Never pass on the White line because it comes first.

**The reader finds the board itself.** A frame, a caption, a whole web page around the board are not a problem, several boards on one page are handled, and there is nothing to tune. Typical run is well under a second. ([How](references/rationale.md#the-recognizer).)

**A reading it is not sure of is withheld, not returned.** Every square carries a softmax score and the board is only as good as its weakest one; below `0.75` the reading is reported as `not trusted` and nothing is returned. This exists because legality does not catch a misread piece — a rook read as a bishop leaves a perfectly legal position and a wrong answer with no symptom. `--confidence 0` accepts anything, and is only worth using when the result will be checked square by square anyway.

**The floor is the last line of defence, not the first.** A board locked one square off on both axes is moved back by the reader itself; the one-king-a-side test, the legality check and the comparison sheet in step 4 catch most of what remains. ([Numbers](references/rationale.md#the-recognizer).)

**Castling rights are read, not assumed** — inferred from the home squares, where king and rook still in place keep the right. The inference errs in one direction only: a king that moved and came back is credited with rights it does not have. The halfmove clock is still written as `0` and is still a claim rather than a blank.

The recognizer needs a flat 2D diagram. It is unreliable on photographs of physical boards taken at an angle, and on very small diagrams. Measured on python-chess's own piece set, renders read correctly down to about 140 px and are refused below that; a refusal is the expected outcome there, not a wrong FEN, and the remedy is a larger crop. Book piece sets have not been measured.

**From the user's FEN:** use it as given, but still run the legality check in step 2 — supplied FENs are often transcribed by hand too. **A placement with no side-to-move field is refused**, not filled in: `chess.Board` accepts it and answers as White, which is the guess this section forbids everywhere else. Ask whose move it is, or read it off the labels.

### Never type a FEN for a position further down a line

The question *what happens after this capture* is answered with `--line`, never by writing out the placement that capture would produce:

```bash
python3 scripts/stage.py "after the sacrifice" -- python3 scripts/solve.py "<FEN>" --line "1.Qd4+ Kh7 2.Qf6"
```

Moves may be SAN or UCI; move numbers and result markers are stripped, so a line pastes in as written. Each move is checked against the board in front of it, and a move that is not legal there stops the run — with the position, the reason and the moves that were actually available.

**Legality cannot catch a hand-typed continuation and never could.** A placement reached by an impossible move is not an illegal position; it is a legal position the game cannot reach from here. So: the FEN is typed once, from the diagram or from the user. Every position after that is reached by playing moves. This is also the cheap route — the alternative is twenty-odd cold-start invocations. ([What this cost once](references/rationale.md#never-type-a-fen-for-a-position-further-down-a-line).)

**When the recognizer fails or cannot be installed**, two browser tools read diagrams well and are worth offering to the user: [fenshot](https://fenshot.com/) runs entirely client-side and uploads nothing — it is the same recognizer `img2fen.py` uses, so it is a way for the user to check a reading rather than a second opinion — and [Chessputzer](https://www.ocf.berkeley.edu/~abhishek/putz) is good on book diagrams, but wants the board border *included* and cropped tightly, the opposite of what `img2fen.py` needs.

### Which side the board is drawn from — settle this first

**Look at the coordinate labels before reading a single piece.** Files `a`–`h` left to right with ranks `8` down to `1`: the normal view, White at the bottom. Files `h`–`a` with ranks `1` up to `8`: the board is drawn **from Black's side**, and two things follow.

**1. The reading has to be turned around.** A Black-view diagram read as if it were normal gives the same position rotated 180° — legal, plausible, and completely wrong: every square has the wrong name, `a8` holds what actually stands on `h1`. Nothing downstream catches this. For the recognizer, pass `--view black` and it rotates the placement itself:

```bash
python3 scripts/stage.py "reading the diagram (img2fen.py)" -- python3 scripts/img2fen.py board.jpg --view black
```

Reading by hand, the rule is just as short: write out all 64 squares in the order they appear in the image (top-left to bottom-right, as always), then **reverse the whole sequence** before cutting it into ranks. `references/reading-diagrams.md` works this through.

**2. The side to move is Black, unless something says otherwise.** Nobody turns a board for the side that is waiting, so a board shown from Black's side is a Black-to-move position — and that is what `--view black` uses by default. The converse does not hold: books print White at the bottom whoever is to move, so the normal view says nothing about the turn, and `img2fen.py` prints a FEN for each side rather than guess. This is a convention rather than a law, so it yields to anything explicit: the user's own statement, a caption, or an arrow marking the last move (an arrow means that side has just moved, so the turn belongs to the other one). Pass the turn as the second argument to override it. What must never happen is the turn being guessed from the position itself — a tactic solved for the wrong side gives a confident answer to a question nobody asked.

**When there are no coordinate labels at all**, the pawns decide: White's pawns advance up the image on a normal view and down it on a Black-view one. `solve.py` applies this test to whatever FEN it is given and warns when the pawns of both sides point the wrong way. It is coarse — silent below three pawns a side and in symmetric structures — so it catches the blunder often, not always. If neither labels nor pawns settle it and the answer depends on it, ask.

## Step 2 — Confirm the position

**Two readings, then legality.** One reading has no check on it at all except legality, and legality is weak.

1. **Read the diagram twice, in different traversal orders** — once rank by rank, once file by file — and compare the two FENs. `references/reading-diagrams.md` gives both procedures. Reading the same image the same way twice reproduces the same error, so the second pass has to go the other way; a file-major pass names the file of every piece explicitly, which is exactly where a rank-major pass goes wrong. When the recognizer has been installed, `img2fen.py` serves as the second reading instead — and a better one, because it fails differently.
2. **Compare piece by piece** where the two disagree. Resolve it by looking at the image again at full resolution, not by picking one.
3. **Legality**: `chess.Board(fen).status()` must return `STATUS_VALID`. `solve.py` does this and refuses to run otherwise.

**Legality is a weak check.** It catches a missing king, a pawn on the first rank, an impossible check — but none of the four errors that actually produce nonsense:

* **A file shift from a miscounted run of empty squares.** The most common error by far: `3p2n1` and `3p3n` both describe a legal rank of eight squares and put the knight on different files. The rank-sum check often recommended for this is worthless — `python-chess` refuses to parse a rank that does not sum to eight, so every FEN reaching the engine has passed it already. Only a second reading catches this.
* **A piece read in the wrong colour.** A white queen taken for a black one leaves a perfectly `STATUS_VALID` position. Count the material of each side against the diagram; a colour swap shows up there and nowhere else. `solve.py` prints the per-side counts to make this quick.
* **A board read from the wrong side.** Legal, and rotated 180°. Verify against the coordinate labels: pick one piece on an edge square, name it from the labels, and check it sits on that square in the FEN.
* **A halfmove clock that is not the game's.** Legality never questions the fifth field (see [above](#where-the-engine-is-the-weak-link)). If the position came from a game and the clock is not known, say the verdict assumes the counter has just been reset.

An illegal position is a diagnostic, not just an error. `OPPOSITE_CHECK` in particular means the side to move is already giving check — usually a wrong FEN, but occasionally the tactical point of the position (a pinned defender that cannot legally capture). Report what the check found rather than silently fixing the FEN.

**Illegality is not evidence of a misread.** Composed problems, textbook fragments and generated diagrams are illegal as a matter of course. The reader returns the position it actually read, illegal or not, and says which rule is broken, in words. So treat an illegal reading as an instruction to compare the diagram against the original, not as a failure of recognition. If they agree, the position is what it is; say so and stop.

**Not every illegality stops the analysis.** Where the engine has nothing to answer — a king missing, both kings attacked at once, a side with two kings — `solve.py` states the reason and does not search. Where the position is merely unreachable from the starting array — excess pawns or pieces, a pawn on the first rank — it says so in one line and analyses normally, because play from that position is ordinary chess and the evaluation is real. Do not report the second kind as a failed reading.

**A legality failure means re-reading the whole position, not patching one square.** The tempting move is to nudge the offending piece to the neighbouring square, watch `STATUS_VALID` appear, and carry on. Do not: a shift on one rank is evidence that the same miscounting habit ran on the other seven. ([What this cost once](references/rationale.md#legality-is-a-weak-check).) The same holds for a FEN the script refuses to parse at all: re-read the position rather than patch the field that failed.

## Step 3 — Search: one command, once

```bash
python3 scripts/stage.py "solving the position (solve.py)" -- python3 scripts/solve.py "5rrk/1p1n3p/4pp1Q/3pP3/p2N3P/P2P2P1/4qPK1/1R5R b - - 0 1"
```

Defaults are tuned for a single-core container and need no flags. One run prints the best move with its evaluation, the second-best move at the same depth, the main line, and the defender's best replies with their own evaluations and lines.

What it does internally, and why:

* **A mate ladder runs before the main search** — `go mate n` for n = 1 up to `--mate-probe` (default 5), `--probe-step` 0.3 s a rung, about 1.7 s on a position with no short mate. A mate it proves outranks the main search, and such a line says `proved by a mate-only search` in place of a depth. A ladder the budget stops says how far it got: `no mate up to N` means N rungs actually ran.
* **When the source announces the length** — "mate in 8", a problem under a diagram, an EPD `bm #9` — **pass it: `--mate-probe N --probe-step 3`.** The default ceiling of 5 sits below the centre of mass of composed problems, so the ladder never asks the question the problem already answered. This costs 25–35 s. Where the mate stays missed at every setting, that is the engine's own limit: report the evaluation and say the mate was not proved.
* **Once a mate in m is in hand, one slow rung asks whether anything shorter exists** (`--reprobe-step`, default 3 s), and the move the main search preferred is kept as the runner-up.
* **+20 or more with no mate triggers one direct query** for a mate in up to `--deep-mate` (default 30, 3 s); a mate it finds replaces the score.
* **The search stops when it converges**, or as soon as a mate is proven; `--time` (default 5 s) is a soft ceiling, not the normal exit.
* **The second-best move comes from the same search** (`MultiPV=2`), so both share a depth; the gap is judged in winning chances rather than centipawns, and mates get their own label. `--no-second` drops it and roughly halves the main search.
* **Defences come from one search after the best move** (`--defences`, default 4). The evaluation after the best move already assumes the best reply: the list explains the win, it does not establish it.
* **All replies are enumerated only when there are few** (`--full-max`, default 8) or a mate has been found; `--scan full` forces it. The list proves a win only when every reply in it is mated.
* **`--budget` (30 s) is a backstop, not a target.**

**`--quick` is not mate-blind; `--fast` is.** `--quick` drops the second line and the defences and keeps the ladder; combining it with `--scan full`, `--defences`, `--defence-time` or `--full-max` is an error rather than a silent override, since those settings would then decide nothing. `--fast` is the old mate-blind behaviour: it prints a line saying the ladder is off and refuses to be combined with `--mate-probe` rather than ignoring it. Use `--fast` only where a mate is out of the question, and prefer `--no-second` when the point is merely speed.

Useful flags: `--line "MOVES"` to analyse the position a sequence of moves reaches, which is the only supported way to look further down a line; `--quick` for the evaluation alone; `--defences N` for a longer list of tries; `--scan full` for the complete enumeration; `--pv-plies` to lengthen the printed line; `--time` and `--min-depth` when a quiet endgame genuinely needs more depth; `--mate-probe` and `--probe-step` to lengthen or disable the ladder, `--reprobe-step` for the slow re-ask that follows a found mate; `--fifty-probe` and `--playout` for the fortress checks above; `--view` to draw the diagram from the source image's side, `--diagram` to force `png`, `svg` or `none`, `--text-board` to print the letter grid as well, `--diagram-path` to choose where the diagram is written; `--timing` for the per-stage breakdown.

### What makes this slow — do not do it

Every one of these has actually cost minutes in practice.

* **Check the stage breakdown before changing any flag.** Nearly every slow run was slow in a stage that no engine flag affects.
* **Do not run the script two or three times.** One invocation produces the whole answer. A second run starts a cold engine with an empty hash table and repeats the entire first search. If more depth is genuinely wanted, raise `--time` on the *first* run. The [50-move probe](#the-50-move-probe-and-what-it-does-not-prove) runs inside the same invocation, so the one case that used to need a second run no longer does.
* **Do not raise `--budget` to hundreds of seconds** "to be safe". The budget does not buy accuracy; it only removes the backstop.
* **Do not launch background deep runs** (`nohup ... --depth 30 --budget 420`) and then wait on them. That pattern is where fourteen-minute analyses come from.
* **Do not ask for `MultiPV` over every legal move.** MultiPV suppresses the cutoffs that make the search fast; over thirty moves it costs about as much as thirty full searches.
* **Do not run the engine by hand** through `printf ... | stockfish` with a fixed `sleep`: the search is either truncated or waited on for nothing.
* **Do not explore side lines by typing a FEN per position.** `--line` reaches them in the same invocation, on a warm hash table, with every move checked.
* **Do not install the recognizer runtime when no image needs recognizing.** It costs seconds rather than minutes now, so it is a small saving — but it is still work nobody asked for.
* **Do not run a command outside the wrapper** once the journal is started. A step that is not measured does not appear in the report, and the total then quietly understates the work.
* **Do not pipe, redirect or post-process the wrapper's output.** `stage.py` is transparent — it passes the child's stdout and stderr through unchanged and propagates its exit code — so the output is ordinary text meant to be read where it lands. Any JSON around it belongs to the surrounding tool harness; `stage.py` contains no JSON at all. Piping the wrapper into a parser destroys a completed analysis and buys nothing.

## Step 4 — Report

**Close the journal before writing the answer:** `python3 scripts/stage.py --stop`. It is silent, it costs nothing, and it is the difference between a table that measures the analysis and one that measures how long the user took to ask about it. The mark is not final — the next wrapped command cancels it, so a follow-up question needs no undoing, only another `--stop` when that answer is done.

### Confirm the reading first

`solve.py` renders the position it was given as a real diagram before anything else and prints the path it wrote — `board.png` when a rasteriser is installed, `board.svg` when none is — with per-side material counts underneath: a swapped colour is visible on the rendered board, a piece dropped from the reading altogether is not, and the counts catch both.

**When the position came from an image, pass the image's side — `--view black` or `--view white` —** so the diagram faces the way the source does. By default it faces the side to move, and a Black-to-move book diagram would come out upside down against its source. `compare.py` takes the same `--view`.

**Open that diagram, then show it in the answer.** Both halves matter. Opening it is the check — the file is a PNG precisely so it can be read here and compared against the source square by square. Showing it is what lets the user catch a misread without being asked; a file rendered and never displayed checks nothing.

**When the position came from an image, do that comparison on one sheet:**

```bash
python3 scripts/stage.py "building the comparison (compare.py)" -- python3 scripts/compare.py board.jpg "<FEN>" -o /mnt/user-data/outputs/compare.png
```

`compare.py` locates the board inside the source image, crops it to its outer edge, scales both boards to the same size and rules the same 8×8 grid over each, so a square is at the same point in both halves. Show this sheet in place of the bare rendered diagram; it needs Pillow and NumPy and says so if they are missing.

The board is found by colour, with a second path for monochrome diagrams. Where neither works — a photograph of a physical board, most often — the script shows the source whole and says the grids may not line up. `--no-crop` forces that; `--view black` (or `--flipped`) is for a diagram drawn from Black's side.

**The rendered board is grey by default**, not python-chess's brown, and the source half is left exactly as it arrived. That asymmetry is the point: the source is the evidence, so process the rendering and never the original. `--no-mono` goes back to the paired brown. ([Why](references/rationale.md#the-comparison-sheet).)

**A comparison sheet is not a substitute for reading the position twice.** It catches a piece on the wrong square, which is what it is for. It cannot catch a board read from the wrong side — a 180° reading puts every piece in a plausible place, and both halves will look alike. Step 2 is what catches that.

**When the diagram is an SVG, that first half is not available** — an SVG cannot be opened here. The material counts stand in, together with the letter grid `chess.svg` writes into the file's `<desc>` element, which `head` will show; `--text-board` prints that grid alongside the diagram whenever a reading is in doubt. Better, install a rasteriser and re-run. **In a plain-text surface, pass `--diagram none`** — a path to a file nobody can open is worse than the letter grid, and that flag prints the grid in its place; the same fallback fires by itself when the file cannot be written.

**Do not imitate a board in text**, and do not draw one by hand: box-drawing characters and glyphs like `♞` misalign outside a monospace terminal, and a check that looks broken is not looked at. Show the rendered file.

Whether to *stop and wait* for the user is a judgement: never stopping lets a misread reach the answer, and stopping every time trains the user to wave the check through. So:

* **Show the rendered diagram every time** the position came from an image. This costs the user nothing and lets them catch a misread without being asked.
* **Stop and wait** when there is an actual reason to doubt: the two readings disagreed, legality failed on the first attempt, the diagram is cluttered or is a photograph of a physical board, the orientation was not settled by coordinate labels, or the material count looks wrong for the position.
* **Otherwise state the verdict**, with the diagram shown alongside it.

The user's own correction outranks all of this. When they say a square is wrong, re-read the whole position rather than moving the one piece.

### Then the verdict

Give the idea, not a transcript. A good answer explains *why* the move works — a pinned defender, an overloaded piece, a mating net — and then supports it with the line. Structure that works:

1. The move, with the mechanism in one sentence.
2. The defender's main tries and why each fails, taken from the reply list.
3. The evaluation, and the distance to the second-best move. The script labels the gap itself — `lead`, `difference … within search noise`, `only this move mates`, `the second move mates too`, `decisive gap: the second move loses to mate` — and the label is what to report, not the centipawns: `difference +3.00 … within search noise` is not a contradiction, it is what three pawns are worth in a position already won by fifteen. Where the label says the moves are equivalent, say plainly that both are playable. **The second-best move comes with an evaluation, not with a refutation:** the run prints its score and nothing else. The gap supports calling the solution unique; it does not support explaining *why* the alternative fails, and that must not be reconstructed from the number. If the reason matters, search the position after that move — one extra `--quick` run — and say the line came from it.
4. If relevant, which earlier move created the problem.
5. The rendered diagram and the Lichess link that `solve.py` produces. Whenever the position was read from an image, show the diagram — it sits in the same view as the original and needs no click, which is why it gets compared and a link often does not. The link is for replaying the line.
6. **Only when the run was slow enough to notice**, one short closing line offering the per-stage timing — see [Timing](#timing). Never the table itself unasked.

**A proof outranks the assistant's own analysis.** `Verdict: the win is forced` appears only when every reply was mated or the headline itself is a mate. Reasoning that arrives at the opposite conclusion is wrong; find where by playing the moves with `--line`, one disagreement at a time, and do not talk that verdict down. `every reply is decisive by evaluation` is an engine opinion — what a fortress produces — and is weighed against the probe and the playout. ([What this cost once](references/rationale.md#the-verdict).)

Be precise about what was proved. When the reply list is the top-N sample, the honest claim is that the advantage survives the defender's best try — not that every defence has been refuted one by one. Only a full enumeration in which every reply is mated supports the stronger claim, and if it left replies marked `not scored`, the script says the proof is incomplete and so should the answer.

When the run printed a re-probe note — *a mate in 6 was found first … that proved a mate in 4* — report the shorter distance and nothing about the longer one. The note exists so the assistant does not have to reconcile two mate scores in the same output; it is not a finding to pass on to the user, who only ever wanted the fastest win.

Report evaluations as they are: `+7.2` for Black means Black is winning by roughly seven pawns, `mate in 19` means a forced mate exists but is long. Do not round a forced mate down to "winning" or inflate a small advantage.

**Below eight pieces, the tablebase is the verdict when it answered.** The `Tablebase (Lichess Syzygy, exact)` block is a proof, and it outranks every engine number in the same output — the run repeats it as its last line so that it cannot be lost under them. Report its result (won, drawn, lost), the best moves it lists, and the distance to mate as `mate in N`. Two categories need care: a *cursed win* is won on the board but drawn by the fifty-move rule, and a *blessed loss* the reverse — say which, and that the halfmove clock decides it, since the clock from a diagram is an assumption. DTM counts as if the fifty-move rule did not exist; DTZ is the number the rule is measured against. The engine line is still useful for explaining the plan, never for the result.

**When the tablebase did not answer, name the ending; do not let the number stand alone.** Without it the engine's score in a theoretically decided ending is a search artefact. Say which ending it is and what theory says, use the engine for the move order, and hand the user the exact answer: the Lichess link `solve.py` prints shows the tablebase in the analysis board's explorer panel, and `https://tablebase.lichess.ovh/standard?fen=<FEN, spaces as underscores>` is the same data as JSON — result, distance to zeroing, distance to mate and every legal move ranked. If the run said the allowlist refuses the host, add one sentence on the setting ([Exact endgames](#exact-endgames-the-one-network-setting)).

**When most of the reply list is mated and the headline is not, believe the reply list.** The script says this itself in place of the verdict line that would contradict it, on both the sampled and the full-enumeration paths. A defence that is mated proves the position mates at least down that branch; a headline in centipawns only means the search did not resolve the others, and the verdict line derived from it inherits the same error. Say the position is mating and that the distance is not established — and do not try to fix it with settings, which does not work. ([The position this was written on](references/rationale.md#the-verdict).)

### Language and notation

Write the answer in the user's language. **Move notation stays international in every language** — `Qc4+`, `Rxb8`, `Ne5` — because that is what `python-chess` emits, what Lichess shows, and what the user can paste anywhere. Do not transliterate piece letters into a local alphabet unless the user asks; if they do, use the standard mapping for that language and watch for the collisions such mappings usually contain.

The scripts print English. Their output is meant to be read by the assistant and translated into the answer, not quoted verbatim.

## Timing

The journal records the whole chain — installs, diagram reading, every `solve.py` run with its internal stages — and it runs on every analysis because it cannot be started retroactively.

**It has to be stopped.** `--stop` ends the span after the last command; a later command reopens it. A report on a journal that was never stopped still prints, but its coverage line says the number includes idle time, so the failure is visible rather than silent. ([Why this was added](references/rationale.md#timing).)

**Do not print the table unless the user asks for it.** A ten-row breakdown after every puzzle is noise, and much of the total is usually the assistant thinking between commands rather than work the user cares about.

**But say the table exists when the run was slow enough to matter** — an install, a wait the user noticed, or the budget warning — with one short closing line such as *"I can show where the time went, if that's useful"*. Never after a quick answer, and never the table itself unasked.

When they do ask:

```bash
python3 scripts/stage.py --report
```

Give it whole when giving it at all — installs, diagram reading, every run with its stages, and the remainder row — and note what dominates if a line genuinely needs explaining.

The remainder row is split into gaps, each named after the command that followed it. A large gap is either a step that was never bracketed — the diagram read by hand, most often — or the assistant composing between calls; the table cannot tell them apart, so say which. `references/timing.md` has the mechanics.

## When the answer is not a puzzle

The same pipeline serves other questions. For "who stands better and why", run `--quick` and report the evaluation with the main plans for both sides. For "was this move a mistake", analyse the position before and after and compare evaluations — two `--quick` runs are enough, and they keep the mate ladder, so the comparison is not mate-blind; do not reach for `--fast` here. For opening positions, note that the engine's preference is not the same as theory and say so.

Quiet and endgame positions are where evaluations drift with depth. If the assessment matters, raise `--time` and `--min-depth` together and say which depth the number came from. In an endgame, check the piece count first: at seven or fewer, depth is the wrong tool and the tablebase in step 4 is the right one.

## Reference

`references/reading-diagrams.md` — how to read a diagram into FEN by hand when the recognizer is unavailable or wrong, with the sanity checks that catch the usual errors.

`references/timing.md` — the timing journal: what it records, how to bracket steps that have no command, how to read the table, and when to offer it.

`references/testing.md` — the regression suites, the matetrack baseline, the positions no suite covers, and what each test file is for. Only needed when editing the scripts.

`references/rationale.md` — the evidence behind the rules above: the positions they were derived from, the measurements, and the approaches that were tried and did not work. Read it when changing a rule, not when applying one.
