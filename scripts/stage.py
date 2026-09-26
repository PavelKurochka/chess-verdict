#!/usr/bin/env python3
#
# chess-verdict -- a Stockfish verdict on a chess position
# Copyright (C) 2026  Pavel Kurochka <https://github.com/PavelKurochka>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Timing journal for the whole chain of work, not just the engine search.

Most of the time in analysing a position is spent outside the engine --
installing packages, importing TensorFlow, repeated runs. So time is recorded
per command, and the internal stages of solve.py and img2fen.py are nested
underneath their own command.

    python3 scripts/stage.py --start                    # begin the journal (silent)
    python3 scripts/stage.py "install engine" -- apt-get install -y stockfish
    python3 scripts/stage.py --begin "reading the diagram"   # step with no command
    python3 scripts/stage.py --end                      # close the last open step
    python3 scripts/stage.py --note "checked by hand" "not measured"
    python3 scripts/stage.py --stop                     # work is done (silent)
    python3 scripts/stage.py --report                   # print the table

The journal is cheap and silent, so --start runs at the beginning of every
analysis. The table is NOT part of a normal answer: print it only when the
user asks how long something took. Starting the journal late is not
recoverable -- installs and diagram reading would already be outside it --
which is why the recording is always on and only the printing is on demand.

Steps that have no command of their own (reading the diagram straight off the
image, thinking a line through, interpreting the engine's reply) are bracketed
with --begin/--end so they carry a real duration instead of a dash.

A note is not a separate column: it is appended to the label after a comma, so
the label reads as one phrase.

The total is wall-clock: --report measures from --start to --stop, subtracts
everything accounted for, and puts the remainder in a row of its own.

That remainder is broken down under itself, one line per gap, named by the
command the gap sits in front of. A single "other: 60 s, 69%" says only that
something was slow somewhere, which is not a diagnosis; the same 60 s split into
"12 s before img2fen.py, 21 s before compare.py" says where the time went and
whether it was work or waiting. The arithmetic needs nothing new in the file --
every command row already carries both its duration and the moment it closed, so
the gap in front of it is a subtraction that was simply never done. It also
recovers steps that should have been bracketed with --begin/--end and were not:
an unbracketed step does not vanish into the pool any more, it shows up as a
named gap in front of whatever ran next.

--stop is what ends the measured window, and it belongs immediately after the
last command of the analysis -- before the verdict is written, not after. The
clock used to run to the moment the table was printed, which meant that a user
who asked for the table an hour later was told the analysis took an hour: the
wait for their own next message landed in the "other" row and drowned every real
measurement. Any command recorded after a --stop cancels it, so a follow-up
question simply reopens the journal; stop again when that answer is done. When
--stop was never called the report falls back to the old behaviour and says so
in the coverage line, since a total that silently includes idle time is the bug
this mark exists to prevent.

--stop closes any step still open from --begin, because a bracket left open at
the end of the work is a step that would otherwise vanish from the table.

Journal file: $CHESS_TIMELINE or /tmp/chess-verdict-timeline.tsv.
"""

import os
import subprocess
import sys
import time

JOURNAL = os.environ.get("CHESS_TIMELINE", "/tmp/chess-verdict-timeline.tsv")
MARKS = JOURNAL + ".mark"

TEXT = {
    "spare": "other: gaps not covered by a measurement",
    "gap_before": "before {label}",
    "gap_tail": "after the last command",
    "gap_tail_open": "since the last command, still running",
    "header": "\nTotal time:",
    "total": "TOTAL",
    "coverage": "  Coverage: from the start of the journal to the end of the "
                "work. The report and the text of the answer are outside it.",
    "coverage_open": "  Coverage: from the start of the journal to this table -- "
                     "the work was never closed with --stop, so any time spent "
                     "waiting before the table was asked for is inside the "
                     "'other' row.",
    "empty": "Journal is empty: it was never started (--start), "
             "or no command has run yet.",
    "orphan": "not wrapped by stage.py",
    "orphan_note": "script run outside the wrapper",
    "no_mark": "no open step: run --begin <label> first",
    "need_label_begin": "a label is required: --begin <label>",
    "need_label_note": "a label is required: --note <label> [note]",
    "usage": 'usage: stage.py "<label>" -- <command>',
    "no_cmd": "no command after --",
    "exit_code": "exit code {code}",
    "started": "Timing journal started: {path}",
    "stopped": "Timing journal stopped after {sec:.1f} s of work.",
    "stop_no_journal": "no journal to stop: run --start first",
    "closed_by_stop": "closed by --stop",
}

def t(key, **kw):
    s = TEXT[key]
    return s.format(**kw) if kw else s


def unit(sec):
    return f"{sec:6.1f} s"


def merge(label, note):
    """Label and note read as one phrase rather than two columns."""
    return f"{label}, {note}" if note else label


def clean(text):
    return " ".join(str(text).split())


def append(level, label, seconds, note=""):
    """One journal row. Level 0 is a command, level 1 a stage inside it.

    The fifth field is when the row was closed; the overall span is derived
    from it. solve.py and img2fen.py write four fields, which is allowed.
    """
    if not os.path.exists(JOURNAL):
        return
    with open(JOURNAL, "a", encoding="utf-8") as f:
        sec = "" if seconds is None else f"{seconds:.3f}"
        f.write(f"{level}\t{clean(label)}\t{sec}\t{clean(note)}\t{time.time():.3f}\n")


def started_at():
    """When the journal was switched on, taken from its header row."""
    if not os.path.exists(JOURNAL):
        return None
    with open(JOURNAL, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#start\t"):
                try:
                    return float(line.split("\t", 1)[1])
                except ValueError:
                    return None
    return None


def last_row_time():
    """When the last measured row closed, from its fifth field.

    Only for --stop --at-last, which repairs a journal where the stop was
    forgotten. Rows written by solve.py and img2fen.py carry four fields rather
    than five, so a missing timestamp is skipped rather than treated as zero.
    """
    if not os.path.exists(JOURNAL):
        return None
    last = None
    with open(JOURNAL, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 5 and parts[4]:
                try:
                    last = float(parts[4])
                except ValueError:
                    pass
    return last


def stopped_at():
    """When the work was declared finished, or None if it still is not.

    A stop mark is only honoured when no measured row follows it. That is what
    lets a follow-up question reopen the journal without anyone having to undo
    anything: the next recorded command simply invalidates the earlier stop, and
    the report goes back to running to the present moment until --stop is called
    again.
    """
    if not os.path.exists(JOURNAL):
        return None
    mark = None
    with open(JOURNAL, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#stop\t"):
                try:
                    mark = float(line.split("\t", 1)[1])
                except ValueError:
                    mark = None
            elif line.startswith("#"):
                continue
            elif len(line.rstrip("\n").split("\t")) >= 4:
                mark = None
    return mark


def read():
    """Journal -> list of commands, each with its internal stages.

    Inner rows are written before their own command: the child process ends
    before the wrapper closes its measurement. So pending stages attach to the
    next command that appears.
    """
    if not os.path.exists(JOURNAL):
        return []
    outer, pending = [], []
    with open(JOURNAL, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            level, label, sec, note = parts[0], parts[1], parts[2], parts[3]
            sec = float(sec) if sec else None
            end = None
            if len(parts) >= 5 and parts[4]:
                try:
                    end = float(parts[4])
                except ValueError:
                    end = None
            if level == "1":
                pending.append((label, sec, note))
            else:
                outer.append({"label": label, "sec": sec, "note": note,
                              "end": end, "inner": pending})
                pending = []
    if pending:
        outer.append({"label": t("orphan"), "sec": None, "end": None,
                      "note": t("orphan_note"), "inner": pending})
    return outer


GAP_FLOOR = 0.05


def gaps(rows, begin, end, closed):
    """The unmeasured time, split by which command it sat in front of.

    A gap is the distance from the close of one command to the start of the
    next, and the start is the close minus the duration -- both already in the
    journal. A row with no closing timestamp (an orphan, or a row written by a
    child process) cannot anchor the arithmetic, so its own duration is stepped
    over instead; that keeps measured work out of the gaps rather than letting
    it inflate the next one.

    Gaps below GAP_FLOOR are dropped. They are round-trip noise, one line each
    would bury the two or three that matter, and the pooled 'other' row above
    still carries the exact total.
    """
    if begin is None:
        return []
    out, prev = [], begin
    for r in rows:
        if r["end"] is None:
            prev += r["sec"] or 0.0
            continue
        gap = r["end"] - (r["sec"] or 0.0) - prev
        if gap >= GAP_FLOOR:
            out.append((t("gap_before", label=merge(r["label"], r["note"])), gap))
        prev = r["end"]
    tail = (end if end is not None else time.time()) - prev
    if tail >= GAP_FLOOR:
        out.append((t("gap_tail" if closed else "gap_tail_open"), tail))
    return out


def report():
    rows = read()
    if not rows:
        print(t("empty"))
        return
    measured = sum(r["sec"] for r in rows if r["sec"] is not None)

    begin = started_at()
    end = stopped_at()
    spare = None
    if begin is not None:
        spare = (end if end is not None else time.time()) - begin - measured
        if spare < 0.05:
            spare = None
    total = measured if spare is None else measured + spare

    breakdown = gaps(rows, begin, end, end is not None) if spare is not None else []

    labels = [merge(r["label"], r["note"]) for r in rows] + [t("total")]
    if spare is not None:
        labels.append(t("spare"))
    width = max([len(x) for x in labels]
                + [len(merge(n, note)) + 4 for r in rows for n, _, note in r["inner"]]
                + [len(name) + 4 for name, _ in breakdown])

    def line(label, sec, note, indent=2):
        if sec is None:
            share, shown = "    ", f"{'--':>6}  "
        else:
            share = f"{sec / total * 100:3.0f}%" if total > 0 else "  - "
            shown = unit(sec)
        pad = width - (indent - 2)
        print(f"{' ' * indent}{merge(label, note):<{pad}}  {shown}  {share}".rstrip())

    print(t("header"))
    for r in rows:
        line(r["label"], r["sec"], r["note"])
        for name, isec, inote in r["inner"]:
            shown = f"{'--':>6}  " if isec is None else unit(isec)
            print(f"      {merge(name, inote):<{width - 4}}  {shown}".rstrip())
    if spare is not None:
        line(t("spare"), spare, "")
        for name, sec in breakdown:
            print(f"      {name:<{width - 4}}  {unit(sec)}".rstrip())
    print(f"  {t('total'):<{width}}  {unit(total)}")
    if begin is not None:
        print(t("coverage" if end is not None else "coverage_open"))


def mark_begin(label):
    with open(MARKS, "a", encoding="utf-8") as f:
        f.write(f"{clean(label)}\t{time.time():.3f}\n")


def mark_end(note):
    if not os.path.exists(MARKS):
        print(t("no_mark"), file=sys.stderr)
        return 2
    with open(MARKS, encoding="utf-8") as f:
        lines = [x for x in f.read().splitlines() if x.strip()]
    if not lines:
        print(t("no_mark"), file=sys.stderr)
        return 2
    label, ts = lines[-1].split("\t")
    with open(MARKS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[:-1]) + ("\n" if lines[:-1] else ""))
    append(0, label, time.time() - float(ts), note)
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if args[0] in ("--start", "--reset"):
        with open(JOURNAL, "w", encoding="utf-8") as f:
            f.write(f"#start\t{time.time():.3f}\n")
        if os.path.exists(MARKS):
            os.remove(MARKS)
        # Silent by default: starting the journal is routine, and a line of
        # output here would appear in every single run.
        if "--verbose" in args:
            print(t("started", path=JOURNAL))
        return 0

    if args[0] in ("--stop", "--finish"):
        if not os.path.exists(JOURNAL):
            print(t("stop_no_journal"), file=sys.stderr)
            return 2
        # An open bracket at the end of the work is a step that would otherwise
        # be dropped, so close them all first -- and before the mark is written,
        # or the rows they append would invalidate it.
        while os.path.exists(MARKS) and os.path.getsize(MARKS) > 0:
            mark_end(t("closed_by_stop"))
        # --at-last backdates the mark to the end of the last measured command,
        # for a journal where the stop was forgotten and the idle time has
        # already accumulated. It is a repair, not the normal path: it discards
        # whatever unbracketed work happened after that command.
        when = time.time()
        if "--at-last" in args:
            when = last_row_time() or when
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(f"#stop\t{when:.3f}\n")
        if "--verbose" in args:
            begin = started_at()
            if begin is not None:
                print(t("stopped", sec=time.time() - begin))
        return 0

    if args[0] == "--report":
        report()
        return 0

    if args[0] == "--begin":
        if len(args) < 2:
            print(t("need_label_begin"), file=sys.stderr)
            return 2
        mark_begin(args[1])
        return 0

    if args[0] == "--end":
        return mark_end(args[1] if len(args) > 1 else "")

    if args[0] == "--note":
        if len(args) < 2:
            print(t("need_label_note"), file=sys.stderr)
            return 2
        append(0, args[1], None, args[2] if len(args) > 2 else "not measured")
        return 0

    if "--" not in args:
        print(t("usage"), file=sys.stderr)
        return 2
    cut = args.index("--")
    label = " ".join(args[:cut]) or "command"
    cmd = args[cut + 1:]
    if not cmd:
        print(t("no_cmd"), file=sys.stderr)
        return 2

    started = time.time()
    code = subprocess.run(cmd).returncode
    append(0, label, time.time() - started,
           "" if code == 0 else t("exit_code", code=code))
    return code


if __name__ == "__main__":
    sys.exit(main())
