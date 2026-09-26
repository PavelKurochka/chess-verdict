# Reading a diagram into FEN by hand

Use this when the recognizer is unavailable, when it fails on the image, or as the independent second reading that step 2 of the skill asks for.

## Procedure

Go rank by rank from 8 down to 1, and within each rank from file a to file h — that is exactly FEN order, so no reordering is needed at the end.

For each rank write out all eight squares explicitly before compressing:

```
rank 8:  .  .  .  .  .  r  r  k   →  5rrk
rank 7:  .  p  .  n  .  .  .  p   →  1p1n3p
```

Compressing straight from the picture is where digits get miscounted. Writing the eight symbols first makes the count self-checking.

Uppercase is White, lowercase is Black: `K Q R B N P` / `k q r b n p`.

## The second reading — by files, not by ranks

One reading is not enough, and reading the same image the same way twice is barely better than reading it once: the second pass repeats the first pass's habits and reproduces its errors. Change the traversal order instead.

Go **file by file**, `a` through `h`, and within each file from rank 1 up to rank 8, naming every piece with its square:

```
file a:  a2 B
file b:  b8 r
file c:  c1 b, c5 r
...
```

This works because it attacks the specific thing that fails. A rank-major reading assigns files implicitly, by counting a run of empty squares — and a run miscounted by one shifts a piece sideways into a position that is legal, parses cleanly, and gets a confident wrong answer. A file-major reading names the file of every piece explicitly, so there is no run to miscount.

Convert the file-major list to a FEN and compare the two strings. They agree or they do not; there is nothing to interpret. When they disagree, look at the specific squares in the original image at full resolution — do not average the two readings and do not pick the one that looks nicer.

Both readings are cheap. The comparison is the point: a single reading has no check on it at all except legality, and legality is weak.

## Checks that catch real errors

- **A second reading by files, compared against the first.** See the section above. This is the only check that catches the most common failure — a miscounted run of empty squares, which shifts a piece one file sideways.
- **Exactly one king per side.** Missing kings usually mean a rank was skipped.
- **Pawn count ≤ 8 per side, and no pawns on ranks 1 or 8.**
- **Piece totals are plausible** given the stage of the game. Nine black pieces after a queen sacrifice is suspicious.
- **Material counted separately for each side.** This is the only check that catches a piece read in the wrong colour — a white queen taken for a black one leaves every other check satisfied. The recognizer does make this mistake, and it is invisible in the FEN string itself.
- **`chess.Board(fen).status()` returns `STATUS_VALID`.** This subsumes several of the above and additionally catches an impossible check. It does *not* catch a colour swap, an upside-down board, or a file shift.

**"Each rank sums to 8" is not a check.** It looks like one, and an earlier version of this file recommended it as the main defence against a miscounted empty square. It is worthless: `python-chess` refuses to parse a rank that does not sum to eight (`expected 8 columns per row`), so every FEN that reaches the engine has already passed it. A shifted piece keeps the rank at eight — `3p2n1` and `3p3n` both sum correctly, and one of them puts the knight on the wrong file. Nothing inside the string can distinguish them; only the image can.

## Fields after the board

`<board> <turn> <castling> <en passant> <halfmove> <fullmove>`

- **turn**: `w` or `b`. Never guess it from the position alone. A board drawn from Black's side is Black to move unless something says otherwise; a board in the normal orientation says nothing, since books print White at the bottom whoever is to move. An arrow on the diagram marks the move just played, so the turn belongs to the *other* side. When nothing settles it and the answer depends on it, ask.
- **castling**: read it from the home squares, by the same rule `img2fen.py` applies — king on `e1` with a rook on `h1` gives `K`, with one on `a1` gives `Q`, and the same for Black. Using the same rule as the machine is what keeps the two readings comparable in step 2; a hand reading that writes `-` by habit disagrees with every position whose king and rooks are at home. The rule errs one way only — a king that moved and came back keeps rights it does not have — so a caption, the game score or the user outranks it.
- **en passant**: `-` unless the previous move was a double pawn push and a capture is actually available.
- **halfmove / fullmove**: write `0 1`, but know that the `0` is an assumption, not a neutral value. The engine applies the fifty-move rule inside its search: the same K+B+N ending evaluates `+2.57` with the clock at `0` and `0.00` at `90`. If the position came from a game and the count is unknown, say the verdict assumes it has just been reset. The fullmove number affects nothing.

## Board orientation — check it before reading anything

The procedure above assumes the usual view: White at the bottom, files `a…h` left to right, ranks `8…1` top to bottom. Puzzle sites and some books turn the board towards the side to move, so a Black-to-move diagram can arrive the other way round: **files `h g f e d c b a` left to right, ranks `1…8` top to bottom**.

Read such a diagram as if it were normal and the result is the true position rotated 180° — a legal, ordinary-looking position in which every square carries the wrong name. `status()` returns `STATUS_VALID`, the engine answers confidently, and the answer is worthless.

### Reading a Black-view diagram

Same procedure, one extra step. Write out all 64 squares in image order — top-left to bottom-right, exactly as before — and then **reverse the whole sequence** before cutting it into ranks of eight. Reversing the 64-square list is precisely the 180° rotation: the last square written down is `a8`, the first is `h1`.

```
image, top row (h1 … a1):  R  .  .  .  .  .  K  .
...
image, bottom row (h8 … a8):  .  .  .  .  r  .  k  .

64 squares reversed → cut into ranks 8…1 → normal FEN placement
```

Equivalently, and often easier by eye: read the image **backwards** — bottom-right square first, then right to left along the bottom row, then upward. That produces FEN order directly.

The turn is `b` in this case, unless the user, a caption, or an arrow says otherwise.

### When the labels are missing

The pawns give the direction: White's pawns advance toward Black's side, so on a normal view White's pawns are lower in the image than Black's, and on a Black-view one they are higher. Castled kings help too — a White king on `g1` or `c1` sits at the bottom of a normal view. Neither is proof: a symmetric structure or a pawnless endgame settles nothing, and then the orientation has to come from the user.

`solve.py` runs the pawn test on every FEN it is given and warns when the two sides' pawns point the wrong way, but it stays silent with fewer than three pawns a side. Treat it as a net, not as a check.

## When the recognizer and the manual reading disagree

Look at the specific squares that differ, in the original image, at full resolution. Do not average the two readings and do not default to the machine. The disagreement is almost always on one or two squares and is quick to settle.
