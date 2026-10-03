# chess-verdict, for people who don't write code

*You show it a chess position. It tells you the move — and how sure that answer
really is.*

This page explains what the skill does and how to read what it says back. It
assumes you play chess and that you have no interest in Python. Nothing here
requires you to type a command; the commands in the other files are for the
assistant, not for you.

---

## What it is

`chess-verdict` gives Claude a chess engine — Stockfish, the same one behind the
analysis board on Lichess — plus a set of rules about how to use it and what it
is allowed to claim afterwards.

Two habits separate it from just asking an assistant "what's the best move here".

**It checks that it read the board correctly before it analyses anything.** A
misread piece produces a position that is perfectly legal and completely wrong,
and the engine will then answer that wrong position with total confidence.
Nothing later in the process catches it. So every run starts by drawing the
position it thinks it has and counting the material on each side, and it shows
you both.

**It separates "winning" from "proved".** An engine number like +3.5 means the
engine likes White. It does not mean the win is forced. The skill checks the
defender's replies and ends every run with a line saying which of the two it
actually established.

---

## How to use it

In the Claude app: **Customize → Skills**, upload `chess-verdict.zip`. After
that it turns itself on when a position comes up. You do not have to mention it,
and you do not have to say the words "Stockfish", "engine" or "FEN".

Pick **Opus or Sonnet** in the model menu, not Haiku. Haiku finds the same
moves, because the engine does that part, but in testing it mixed two
alphabets in the piece letters, made wrong claims about the moves, and did not
check the board it showed you.

Then just show a position and ask, in whatever words you'd use with a person:

- a screenshot of a board, or a photo of a diagram in a book — "what should
  White play?"
- a FEN string — "is this actually winning or am I fooling myself?"
- a position from your own game — "was Rxe6 a mistake?"
- "who stands better here, and why?"
- "is this sacrifice sound?"

A typical position takes a few seconds. If an answer is taking minutes,
something went wrong with how it was asked, not with the position.

Photographs of a real board, taken at an angle, are the one input that often
fails. A flat screenshot or a scan of a printed diagram works far better.

**One optional setting, for endgames.** With seven pieces or fewer on the
board the exact answer lives in an online database at Lichess. The skill can
look it up only if you let it: in the app's settings, find **Domain allowlist**,
type `tablebase.lichess.ovh` under **Additional allowed domains** and press
**Add**, then start a new chat. That one address is all it needs. If your
account belongs to a company plan, an administrator has to do this. Without it
everything still works; in endgames you get the engine's estimate and a link
to open yourself, and the answer will mention the setting.

---

## Reading the answer

Here is a full run, unedited:

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

Line by line:

**The diagram and the material counts.** This is the part to actually look at.
Put the drawn board next to the one you sent and check they match. Then check
the counts: *White has a queen, two rooks and three pawns; Black has a queen, a
rook, two bishops and two pawns.* A piece read in the wrong colour, or dropped
entirely, still leaves a legal position and a confident answer — the count is
what catches it. Ten seconds here is worth more than any engine setting.

**The Lichess link** opens the same position in a browser if you want to push
the pieces around yourself.

**The halfmove clock note.** Chess has a fifty-move draw rule, and a position
copied from a diagram carries no record of how many moves have passed since the
last capture or pawn move. The skill assumes the counter just reset. In an
endgame that assumption can change the answer, so if the position came from a
real game, say what the real count was.

**`evaluation +3.74`** is measured in pawns, from White's point of view. Plus is
good for White, minus is good for Black; roughly, ±0.5 is a small edge, ±1.5 is
a serious one, ±3 is usually decisive. `mate in 2` replaces the number when
there's a forced mate.

**`depth 17`** is how many half-moves ahead the engine looked. Higher is more
trustworthy. `0.4 s` is how long that took.

**`Second best: Rxb8 +0.03 ... lead +3.71`** answers "is this move unique, or
would something else do?" Here the best move is worth three and a half pawns
more than the next one, so the solution is unique. The bracketed *in chances*
figure rescales that gap by how much it matters: half a pawn decides a level
game and means nothing when you're already up a rook, so the raw difference on
its own would mislead.

**The numbers wobble.** Run the same position again and the evaluation may come
back `+3.55` instead of `+3.74`. The engine stops as soon as its answer settles,
and how far it gets depends on how busy the machine is. The move and the verdict
are what stay put; treat the second decimal as noise.

**`All opponent replies (3)`** is the defender's side. When the opponent has few
enough legal moves, every one of them is checked and listed with what happens
after it. When there are many, only the best few are shown, and the answer says
so.

**The verdict line** is the point of the whole thing. Three forms:

> `Verdict: the win is forced, every reply loses (1).`

Every legal defence was tried and every one of them is mated, or the engine found a forced mate outright. This is a proof.

> `Verdict: the win is not forced; these replies hold: Kh8.`

White is much better and will probably win, but Black has a move that survives.
In the example above, `Rf7` gets mated at once and `Be6` drops a bishop — but
`Kh8` holds on. White wins a piece, not the game by force. That distinction is
exactly what most engine output blurs, and the reason this line exists.

> `Verdict: every reply is decisive by evaluation (4), the weakest at +10.71 -- an evaluation, not a proof.`

Every defence was tried and each one looks lost, but only by the engine's reckoning, not by a mate. A fortress — a position the weaker side can hold for ever despite being far behind — produces exactly this line, so it is a reason to look further rather than an answer: the skill then plays the position out to see whether any progress is actually made.

---

## When to distrust the number

Some of these are limits of chess engines in general, not of this skill, and no
setting removes them.

**Fortresses.** A position can be locked so that the stronger side, however much
material it has, cannot make progress. The engine still reports a huge
advantage. If the evaluation looks decisive but nothing seems to be happening,
ask it to play the position out against itself — it will show you the moves
going nowhere.

**Endgames with very few pieces.** Those have been solved exactly by databases
called tablebases. King, bishop and knight against a lone king is a forced
mate, but the engine reports it as a modest advantage. With the setting above
the skill looks the position up and gives the exact result; without it, trust
the name of the ending over the number, and open the link it gives you.

**Quiet positions.** The engine stops early once its answer stops changing,
which suits tactics. Slow, closed positions keep drifting the deeper you look,
so an answer there should come with the depth attached and be treated as
provisional.

**One useful cross-check:** if the headline evaluation says "small advantage"
but the list of defences underneath shows one of them being mated, believe the
list. It proved something; the headline only estimated.

---

## Words you'll see

- **FEN** — a one-line text encoding of a position, the thing that starts
  `rnbqkbnr/pppppppp/...`. Copyable out of most chess sites.
- **Engine / Stockfish** — the program that calculates. It plays far above any
  human, and it still has the blind spots above.
- **Evaluation, centipawns** — the advantage expressed in pawns; +1.00 means
  "worth about a pawn".
- **Depth / ply** — half-moves of lookahead. One move by each side is two plies.
- **Forced mate** — mate that arrives no matter what the defender does.
- **Tablebase** — a solved database of endgames with few pieces; the only source
  of exact answers there.
- **Fortress** — a position that cannot be broken through despite a material
  deficit.

---

## The other files here

- **README.md** — the same skill described for someone who will run the scripts.
- **SKILL.md** — the instructions the assistant itself follows.
- **FAQ.md** — how this compares with the other chess skill going around, and
  where that one is the better choice.
- **CHANGELOG.md** — what changed in each version, including the things that
  were tried and didn't work.
