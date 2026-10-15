# Showing how a won position is won

Read this when the verdict was "decisive, not forced" — no mate, eight men or more — and the user asks *show how*, brings a plan of their own, or names a defence to test. `SKILL.md` has the rules in four lines; this file has the procedure. The evidence behind it is in [rationale](rationale.md#technique-how-not-whether).

## Contents

- [Why the verdict does not answer this](#why-the-verdict-does-not-answer-this)
- [Before any command: the defender's setups](#before-any-command-the-defenders-setups)
- [The first move](#the-first-move)
- [One run per branch](#one-run-per-branch)
- [Reading a playout](#reading-a-playout)
- [The defender's alternatives](#the-defenders-alternatives)
- [Writing it up](#writing-it-up)

## Why the verdict does not answer this

`solve.py` settles a result: the best move, the score it holds against the defender's best try. A plan is a different claim — that one way of playing wins against *every* way of defending — and a single search cannot show that, however deep.

**The evaluation cannot carry the argument.** A piece up, every sensible plan scores +3 or more, and the number says only that the piece is extra. Two equal scores mean the engine cannot tell the moves apart, not that one of the ideas is refuted. In the chat this file comes from, defences were ranked by centipawns in four answers and the four rankings contradicted each other; the user's objection — "the evaluation is big everywhere, it does not give a plan" — was right. What counts as evidence is progress against the most stubborn defence: a capture, a pawn move, the king breaking in, and above all a position the tablebase calls won.

**A long main line is not a plan either.** `--pv-plies 40` prints the engine's guess for both sides; past the first few moves none of the defender's moves in it was compared with anything. Calling them "the only counterplay" is a claim the run never tested.

## Before any command: the defender's setups

List, piece by piece, what the defender can do, and name each setup by what its pieces do — never by one word for the whole defence ("passive" was used in the chat for a setup whose rook was the most active piece on the board):

- **The king**: towards the attacker's weak pawn; on guard of its own pawns; over to the other wing, giving up a pawn.
- **The rook (or other piece)**: checks from behind; attacks on a pawn; guarding a rank or a file the attacker needs.
- **Pawn breaks**: every pawn move that opens a line. Usually they lose at once — one search each settles it, a playout is not needed.

A setup the user names is a hypothesis to test as stated, from the line they gave last — not from a fresh engine choice, and not after "improving" it.

## The first move

Choose it by the plan: the move that serves every setup. When the run's gap label calls two first moves equivalent, a deeper run that prefers a third one is not news, and a run with `--no-second` cannot rank its move at all — it has no second line to compare with. In the chat the recommended first move changed twice this way, and the second change lost a tempo against the very defence the user raised next.

## One run per branch

"`solve.py` once" is the rule for a verdict. Here each branch is its own position, so each gets one run, through the wrapper as always:

```bash
python3 scripts/stage.py "branch: king on c6-c7" -- python3 scripts/solve.py "<FEN>" --line "1.Rb2 Rh3 2.Rb5 Rg3 3.Rd5" --playout 100 --playout-step 0.5
```

- `--line` reaches the branch point with every move checked. Where it leaves the defender to move, the best and second-best moves are the defender's two best tries, with the gap label between them. Where it leaves the attacker to move, the defences list (four by default, `--defences N` for more) is the defender's best replies — to the engine's best move, which is the plan's next move only if the engine agrees with the plan.
- `--playout 100` plays the branch out, prints the moves and the clock resets, and stops at the first position with seven men or fewer that the tablebase answers. Its time is set aside on top of `--budget`, and the header says how much — 100 plies at 0.5 s is about a minute.
- **Say how long it will take before starting.** Four to six branches is five to ten minutes. The chat's final pass — nine games, every one checked against the tablebase — took about sixteen.

There is no switch that makes the defender *keep* a setup during a playout. To test one, write the defender's moves into `--line` as far as the setup can be kept. Where no legal move keeps it — a check, or nothing else left to move — the setup has failed, and the attacker's move that forced it is the point of the plan. Any count in the answer — how often the setup was left, and why — is read off output, never recalled: "eight times, all in check" in the chat was six checks and two bare-king moves.

## Reading a playout

Report each branch at the level its own output printed, and say which level each branch reached when they differ:

| The playout ended… | What it licenses |
|---|---|
| at a tablebase answer, `for <side> the position is won` | exact from that ply on; the way there is self-play |
| at a tablebase answer after a promotion (the run says so) | the queen is confirmed, the conversion is not |
| at a tablebase draw from a decisive start | the self-play did not convert; find where with `--line`, before calling the position drawn |
| in mate, with no seven-man position on the way | self-play to mate: strong evidence, not proof |
| with the tablebase unreachable (the run says why) | self-play only, however it ended |
| cut short, out of plies, or on a claimable draw | as in `SKILL.md`, the 50-move section |

Self-play is one engine against itself: it is evidence because the burden is one-sided — the engine claimed the win and then made it happen — not because the defence was the best possible. A branch played to an anchor and a branch only walked move by move are not the same strength; in the chat the user noticed the difference before the answer did.

## The defender's alternatives

An alternative whose score is inside search noise — the scale `solve.py`'s gap label uses, about 0.05 in winning chances — is not a refutation of the move played, and not a new defence: usually it is the same setup in another order. Play an alternative out when it is a different *setup* — the king going the other way, a pawn given up — not merely a different move. In the chat the one setup no earlier answer had considered (the king to the kingside, giving up b6) scored 0.06 in winning chances better than the move played, just past the noise; the other alternatives the chat played out led to the same lost position by other roads.

## Writing it up

The structure the chat's final answer converged on, and the user accepted:

1. **The verdict and the first move**: no forced win, the rest is technique; the first move and why it serves every setup.
2. **One section per setup**, named by what the defender's pieces do, with the options of the defender's active piece inside it. Each section: the plan in steps, then the line — taken from the playout's `Moves:` line, not reconstructed.
3. **The general principle**: what decides the plan (where the defender's king goes) and the white answer to each.
4. **How far it is proved**, split in two: exact — the tablebase anchors, branch by branch; not exact — the way to them, which is self-play.

**When the user brought the plan, the answer is about their plan**: what holds, what fails, where the engine's choice differs — attributed to them. Restating it in other words is not a refinement of it, and calling it "almost the same as mine" was the answer the chat had to take back.
