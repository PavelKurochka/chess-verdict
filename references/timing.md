# The timing journal

The journal answers one question: where did the time actually go? In practice
almost none of it goes to the engine. Installs, a cold container, model loading
starting up, and repeated runs dominate, and each of those is invisible unless
it is measured.

## Contents

- [Recording is always on, printing is on request](#recording-is-always-on-printing-is-on-request)
- [Wrapping commands](#wrapping-commands)
- [Steps that have no command](#steps-that-have-no-command) — `--begin` / `--end`
- [Reading the table](#reading-the-table)
- [Stopping the clock](#stopping-the-clock) — `--stop`
- [Per-run breakdowns](#per-run-breakdowns)

## Recording is always on, printing is on request

`scripts/stage.py --start` runs as the first command of every analysis. It is
silent and costs a fraction of a second.

`scripts/stage.py --stop` ends the measured window. It runs as the last command
of every analysis, immediately before the answer is written.

`scripts/stage.py --report` prints the table. Run it **only when the user asks**
how long something took. It is not part of a normal answer: a ten-row breakdown
after every puzzle is noise, and most of the total is usually the assistant
thinking between commands rather than any work the user cares about.

The split exists because the journal cannot be started retroactively. By the
time someone asks "how long did that take?", the installs and the diagram
reading are already in the past. Recording always, printing rarely, is the only
arrangement that can answer the question later.

That same asymmetry has a cost worth naming: the user cannot ask for something
they do not know is there. Nothing in a normal answer suggests a per-stage
breakdown exists, so "printing on request" collapses into "never printing" for
anyone who has not read this file. The fix is not to print more — it is to
**offer once, at the end of a slow answer**: a single line saying the breakdown
is available, when an install was needed, when the run was long enough that
the user waited, or when the budget warning fired. After a two-second answer,
say nothing: an offer attached to every run is skipped like any other
boilerplate, and then the feature is unreachable again for a different reason.

## Wrapping commands

Once the journal is running, every command goes through the wrapper:

```bash
python3 scripts/stage.py "<label>" -- <command with arguments>
```

The wrapper runs the command unchanged, passes its output and exit code
straight through, and records how long it took. `solve.py` and `img2fen.py`
write their own internal stages into the same journal, so each of their runs
appears as a labelled block with its stages nested underneath.

A command run outside the wrapper does not appear in the report at all, and the
total then quietly understates the work.

## Steps that have no command

Reading the diagram off the image, thinking a line through, interpreting the
engine's reply — these take real time and have no process to measure. Bracket
them:

```bash
python3 scripts/stage.py --begin "reading the diagram from the image, no img2fen.py"
# ... the diagram is read, the FEN written out ...
python3 scripts/stage.py --end
```

The label is the whole description: there is no separate note column, so put
everything into `--begin` and close with a bare `--end`. A note passed to
`--end` is appended after a comma. Marks nest: `--end` closes the innermost open
one. `--note "<label>" "<note>"` records a step that genuinely could not be
measured, but a dash in the table is a hole in the report — reach for bracketing
first.

## Reading the table

```bash
python3 scripts/stage.py --report
```

```
Total time:
  install engine                                              6.1 s   18%
  install python-chess                                        2.5 s    7%
  reading the diagram from the image, no img2fen.py          14.8 s   43%
  solving the position (solve.py)                             2.6 s    8%
      importing python-chess                                  0.1 s
      legality and game-over check                            0.0 s
      engine startup: 1 thread(s), hash 64 MB                 0.5 s
      main search to depth 17, MultiPV 2                      1.7 s
      enumerating all replies: 2 replies, of which searched 2 0.3 s
  other: gaps not covered by a measurement                    8.4 s   24%
      before install python-chess                             2.1 s
      before solving the position (solve.py)                  4.2 s
      after the last command                                  2.1 s
  TOTAL                                                      34.4 s
  Coverage: from the start of the journal to the end of the work. The report
  and the text of the answer are outside it.
```

The total is wall-clock: `--report` measures from `--start` to `--stop`,
subtracts everything accounted for, and puts the remainder in the `other` row —
so a step that was never bracketed cannot vanish, it only becomes anonymous.

Since 2.19.0 it does not stay anonymous either. The remainder is split under
itself, one line per gap, each named after the command it sat in front of. A
single `other: 60 s, 69%` says only that something was slow somewhere, which is
not a diagnosis; the same 60 s split into `12 s before img2fen.py, 21 s before
compare.py` says where the time went. Nothing new is recorded to make this
work — every command row already carries its duration and the moment it closed,
so the gap in front of it is a subtraction that was simply never done.

Read the breakdown as a question about bracketing, not a verdict. A large gap in
front of a command is either a step that has no command of its own and was not
bracketed — the diagram read by hand is the usual one — or the assistant
composing between tool calls. The table cannot tell those apart; the session
can, and should say which.

Gaps below 0.05 s are dropped rather than listed. They are round-trip noise, a
line each would bury the two or three that matter, and the pooled row above
still carries the exact total.

One gap stays open by construction: the answer itself is written after the last
command runs, so the time spent writing it is in no row. `after the last
command` covers only what happened before `--stop`.

## Stopping the clock

```bash
python3 scripts/stage.py --stop
```

Silent, and it belongs immediately after the last command of the analysis —
before the verdict is written, not after.

Before 2.11.0 there was no such command and the span ran to the moment the table
was printed. Since printing happens only on request, that meant the interval
between finishing the work and being asked about it — entirely the user's own
reading and typing — was billed to the analysis. A real session: fifteen seconds
of measured work, a nine-minute pause, and a table reporting **549 s total, 97%
in `other`**, with every genuine measurement displayed as 0%. The one row that
was pure noise dominated the table, and the rows that answered the question
looked negligible.

Three properties make the mark safe to use without thinking about it:

* **A later command cancels it.** A follow-up question reopens the journal by
  itself; stop again when that answer is done. Nothing has to be undone, and
  there is no state to get wrong.
* **An open bracket is closed by it,** with `closed by --stop` appended to the
  label, so a `--begin` without a matching `--end` shows up as a measured row
  instead of disappearing.
* **A journal that was never stopped still reports.** The coverage line then
  says the total includes idle time. A silently wrong number was the original
  bug; a number that describes its own limits is not.

`--stop --at-last` backdates the mark to the moment the last measured command
finished. It repairs a journal where the stop was forgotten — the row close
times are recorded, so the analysis can still be recovered from it — and it
discards any unbracketed work that happened after that command. It is a repair,
not the normal path.

## Per-run breakdowns

`solve.py --timing` and `img2fen.py --timing` print their own stage tables. Both
are off by default and both journal their stages either way, so leaving them off
loses nothing that `--report` needs.

Read `solve.py`'s breakdown as a diagnosis: time in **main search** is the
engine doing its job and is the only line that buys accuracy; time in **engine
startup** above a second means the hash table is too large; a large **defences**
or **enumerating all replies** means the reply work should be narrowed
(`--defences`, or dropping `--scan full`); a large **importing python-chess**
means the container is cold, not that the position is hard.

`img2fen.py`'s breakdown is worth showing when someone asks why reading a
diagram took longer than solving the position: the network itself runs in well
under a second, and essentially all of the time is import and model loading.
